"""Read-only MyRealTrip MCP client. No credentials or product-page scraping.

Public functions return None on transport, MCP or parse failure. Missing values
remain None; date-level inventory never implies a confirmed starting time.
"""
from functools import wraps
import html
import json
import re
import urllib.request

ENDPOINT = 'https://mcp-servers.myrealtrip.com/mcp'
TIMEOUT = 10
PRODUCT_URL = re.compile(r'^https://experiences\.myrealtrip\.com/products/(\d+)$')


def fail_soft(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
            return None
    return wrapped


def rpc(method, params=None):
    try:
        request = urllib.request.Request(ENDPOINT, data=json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}
        }).encode(), headers={'Content-Type': 'application/json',
                              'Accept': 'application/json, text/event-stream'})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode('utf-8')
        if body.lstrip().startswith('data:') or body.lstrip().startswith('event:'):
            messages = [json.loads(line[5:].strip()) for line in body.splitlines()
                        if line.startswith('data:') and line[5:].strip() != '[DONE]']
            envelope = next(x for x in messages if x.get('id') == 1)
        else:
            envelope = json.loads(body)
        result = envelope.get('result')
        return result if isinstance(result, dict) and not result.get('isError') else None
    except (OSError, ValueError, TypeError, StopIteration):
        return None


def call_tool(name, arguments):
    result = rpc('tools/call', {'name': name, 'arguments': arguments})
    if result is None:
        return None
    try:
        text = '\n'.join(c['text'] for c in result.get('content', []) if c.get('type') == 'text')
        try:
            return json.loads(text)
        except ValueError:
            return text or None
    except (KeyError, TypeError):
        return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def text_lines(value):
    if isinstance(value, str):
        return [html.unescape(re.sub(r'<[^>]+>', ' ', value))]
    return [html.unescape(re.sub(r'<[^>]+>', ' ', x['value']))
            for x in walk(value.get('widget', value))
            if x.get('type') in ('Text', 'Title', 'Caption') and isinstance(x.get('value'), str)]


@fail_soft
def parse_search(payload):
    if not isinstance(payload, dict):
        return None
    products = []
    for item in walk(payload.get('widget', {})):
        if item.get('type') != 'ListViewItem':
            continue
        urls = [x['url'] for x in walk(item) if isinstance(x.get('url'), str)
                and PRODUCT_URL.fullmatch(x['url'])]
        lines = text_lines(item)
        if not urls or not lines:
            continue
        rating = re.search(r'⭐\s*([\d.]+)\s*\((?:리뷰\s*)?([\d,]+)', '\n'.join(lines))
        price = re.search(r'([\d,]+)원', '\n'.join(lines))
        products.append({'gid': PRODUCT_URL.fullmatch(urls[0])[1], 'url': urls[0],
                         'name': lines[0], 'rating': float(rating[1]) if rating else None,
                         'reviews': int(rating[2].replace(',', '')) if rating else None,
                         'price': int(price[1].replace(',', '')) if price else None})
    return products


@fail_soft
def search_products(queries):
    found, succeeded = {}, False
    for query in queries:
        products = parse_search(call_tool('searchTnas', {'query': query}))
        if products is not None:
            succeeded = True
            for product in products:
                found.setdefault(product['gid'], product)
    return list(found.values()) if succeeded else None


@fail_soft
def get_detail(gid, url):
    payload = call_tool('getTnaDetail', {'gid': str(gid), 'url': url})
    if payload is None:
        return None
    lines = text_lines(payload)
    meeting = next((s.removeprefix('장소:').strip() for s in lines if s.startswith('장소:')), '')
    # A timetable interval (e.g. 1시간 간격) is not the activity's duration.
    duration = re.search(r'(?:소요\s*시간|체험\s*시간|진행\s*시간)\s*[:：]?\s*(?:(\d+(?:\.\d+)?)\s*시간)?\s*(?:(\d+)\s*분)?', '\n'.join(lines))
    minutes = int(float(duration[1] or 0) * 60 + int(duration[2] or 0)) if duration else 0
    return {'meetingText': meeting[:180], 'durationMin': minutes or 120,
            'durationSource': 'detail' if minutes else 'default',
            'text': '\n'.join(lines)}  # ephemeral: snapshot stores only the meeting line


def start_time(label, date):
    # Seasonal labels must select the requested month's override, not every time.
    month = int(date[5:7])
    seasonal = re.search(rf'(?<!\d){month}월\s*(\d{{1,2}}):(\d{{2}})', label)
    match = seasonal or re.search(r'(\d{1,2}):(\d{2})', label)
    if match:
        h, m = map(int, match.groups())
    else:
        match = re.search(r'(오전|오후)\s*(\d{1,2})시\s*(?:(\d{1,2})분)?', label)
        if not match:
            return None
        h, m = int(match[2]) % 12 + (12 if match[1] == '오후' else 0), int(match[3] or 0)
    return f'{h:02}:{m:02}' if 0 <= h < 24 and 0 <= m < 60 else None


@fail_soft
def parse_options(payload, date):
    if not isinstance(payload, dict) or payload.get('success') is not True:
        return None
    if payload.get('selectedDate', payload.get('searchParams', {}).get('selectedDate')) != date:
        return None
    slots = {}
    for option in payload.get('options', []):
        start = start_time(option.get('name', ''), date)
        if start is None:
            continue
        count = option.get('availablePurchaseQuantity')
        available = (count >= 2 if isinstance(count, (int, float)) else None)
        if payload.get('isRequestedDateAvailable') is False:
            available = False
        slot = {'start': start, 'available': available, 'price': option.get('salePrice'),
                'optionName': option.get('name', ''), 'stock': count}
        # Ambiguous price variants at the same time are not silently chosen.
        if start in slots and slots[start]['price'] != slot['price']:
            return None
        slots[start] = slot
    if not slots and payload.get('isRequestedDateAvailable') is False:
        # Sold-out dates can have empty options but still advertise their time units.
        for unit in payload.get('units', []):
            for item in unit.get('unitItems', []):
                start = start_time(item.get('name', ''), date)
                if start:
                    slots[start] = {'start': start, 'available': False, 'price': None,
                                    'optionName': item.get('name', ''), 'stock': 0}
    return sorted(slots.values(), key=lambda x: x['start'])


@fail_soft
def get_options(gid, url, date):
    return parse_options(call_tool('getTnaOptions', {
        'gid': str(gid), 'url': url, 'selectedDate': date}), date)
