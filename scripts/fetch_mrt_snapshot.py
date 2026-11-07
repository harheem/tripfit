"""Fetch a compact, attributable MCP snapshot. Usage: MRT_DATE=... python ..."""
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from solver import mrt_live as mrt

QUERIES = ['성수 원데이클래스', '성수 공방', '서울 성수 체험', '서울 가죽공방',
           '서울 원데이클래스', '서울숲', '뚝섬']
LOCAL = re.compile(r'(?<!북)서울숲|성수|뚝섬')
# No geocoding is allowed in this task. Unverified local meeting coordinates use
# the requested Seongsu Station fallback (including Seoul Forest meeting places).
# approximate landmark coordinates (meeting points); 서울숲 = 방문자센터 부근, 뚝섬 = 뚝섬역
ANCHORS = {'서울숲': (37.5437, 127.0397), '성수': (37.5446, 127.0557),
           '뚝섬': (37.5473, 127.0473), '잠실': (37.5133, 127.1001),
           '송파': (37.5048, 127.1145), '강남': (37.4979, 127.0276),
           '문래': (37.5170, 126.8946), '성북': (37.5894, 127.0167)}


def fetch_snapshot(date=None):
    date = date or os.getenv('MRT_DATE', '2026-11-14')
    Date.fromisoformat(date)
    schema = mrt.rpc('tools/list')
    required = {'searchTnas': {'query'}, 'getTnaDetail': {'gid', 'url'},
                'getTnaOptions': {'gid', 'url', 'selectedDate'}}
    actual = {t['name']: set(t.get('inputSchema', {}).get('properties', {}))
              for t in (schema or {}).get('tools', [])}
    if not all(fields <= actual.get(name, set()) for name, fields in required.items()):
        return None, 'tools/list 실패 또는 MCP 인자 변경: 기존 스냅숏 유지'
    products, rejected, failures = {}, [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for query, rows in zip(QUERIES, pool.map(lambda q: mrt.search_products([q]), QUERIES)):
            if rows is None:
                failures.append(query)
            for row in rows or []:
                products.setdefault(row['gid'], row)
    if not products:
        return None, '검색 실패 또는 결과 없음: 기존 가상 상품/스냅숏 유지'
    local = [p for p in products.values() if LOCAL.search(p['name'])]
    seoul = [p for p in products.values() if p not in local and
             ('서울' in p['name'] or any(k in p['name'] for k in ANCHORS))]
    candidates = []
    examined = set()
    def inspect(product, require_local):
        name = product['name']
        detail = mrt.get_detail(product['gid'], product['url'])
        if not detail:
            return None, {'name': name, 'reason': '상세 조회 실패: 위치 확인 불가'}
        location = detail['meetingText']
        evidence = name + ' ' + location
        is_local = bool(LOCAL.search(evidence)) and not ('북서울숲' in location)
        # Detail meeting location takes precedence over a keyword in the title.
        if location and not LOCAL.search(location) and any(k in location for k in ('봉은사', '강남', '당산', '문래', '잠실')):
            is_local = False
        if require_local and not is_local:
            return None, {'name': name, 'reason': '실제 집결지가 성수·서울숲·뚝섬으로 확인되지 않음'}
        anchor = next((k for k in ANCHORS if k in location), None)
        anchor = anchor or next((k for k in ANCHORS if k in name), None)
        if anchor is None:
            return None, {'name': name, 'reason': '집결지 근사 위치를 정할 근거 부족'}
        options = mrt.get_options(product['gid'], product['url'], date)
        if options is None or not options:
            return None, {'name': name, 'reason': '날짜별 시작 시각 미반환/조회 제한: 예약 시각을 만들지 않음'}
        # Multi-region products must match the selected meeting area at option level.
        if any(any(k in o['optionName'] for k in ANCHORS) for o in options):
            options = [o for o in options if anchor in o['optionName'] and
                       not (anchor == '서울숲' and '북서울숲' in o['optionName'])]
        if not options:
            return None, {'name': name, 'reason': '해당 날짜·지역에 이용 가능한 시각 없음'}
        lat, lng = ANCHORS[anchor]
        row = {**product, 'durationMin': detail['durationMin'],
               'durationSource': detail['durationSource'], 'meetingText': location,
               'lat': lat, 'lng': lng, 'coordSource': 'approx',
               'coordEvidence': f'{location or name} → ' + f'{anchor} 기준 근사 좌표' + '; 주소 지오코딩 미실시',
               'locationEvidence': f'제목/집결지 지명: {anchor}', 'options': options}
        if not is_local:
            row['note'] = '성수 시각 옵션 상품 없음: 위치를 판정한 서울 후보 중 근사 직선거리로 가장 가까운 상품'
        return row, None

    for batch in (local, seoul):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = pool.map(lambda p: inspect(p, batch is local), batch)
            for product, (row, rejection) in zip(batch, results):
                examined.add(product['gid'])
                if row:
                    candidates.append(row)
                if rejection:
                    rejected.append(rejection)
        if candidates:
            break
    if not candidates:
        return None, '성수 및 서울 후보에서 위치·날짜별 시작 시각을 함께 확인하지 못함: 기존 상품 유지'
    candidates.sort(key=lambda p: (not any(o['available'] is not False for o in p['options']), (p['lat'] - 37.5446)**2 + ((p['lng'] - 127.0557)*0.8)**2))
    picked = candidates[:2]
    for p in products.values():
        if p['gid'] not in examined:
            rejected.append({'name': p['name'], 'reason': '제목의 지역이 성수 인근 아님 또는 위치 근거 부족; 성수 실옵션 상품 우선'})
    for p in candidates[2:]:
        rejected.append({'name': p['name'], 'reason': '가까운 후보 2개 우선'})
    return {'fetchedAt': datetime.now(timezone.utc).isoformat(), 'date': date,
            'queriesTried': QUERIES, 'queriesFailed': failures, 'picked': picked,
            'rejected': rejected}, None


def refresh_snapshot():
    """Refresh selected products, keeping discovery separate from the 10s API budget."""
    from solver.mrt_places import read_snapshot
    previous = read_snapshot()
    if previous is None:
        return fetch_snapshot()
    date = os.getenv('MRT_DATE', previous['date'])
    queries = list(dict.fromkeys('서울숲' if '서울숲' in p['name'] + p['meetingText']
                                else '서울 성수 체험' if LOCAL.search(p['name'] + p['meetingText'])
                                else p['name'] for p in previous['picked']))
    schema = mrt.rpc('tools/list')
    required = {'searchTnas': {'query'}, 'getTnaDetail': {'gid', 'url'},
                'getTnaOptions': {'gid', 'url', 'selectedDate'}}
    actual = {t['name']: set(t.get('inputSchema', {}).get('properties', {}))
              for t in (schema or {}).get('tools', [])}
    if not all(fields <= actual.get(name, set()) for name, fields in required.items()):
        return None, 'MCP 인자 확인 실패: 기존 유지'
    products = mrt.search_products(queries)
    if products is None:
        return None, '상품 검색 실패: 기존 유지'
    by_id = {p['gid']: p for p in products}
    picked = []
    for previous_product in previous['picked']:
        product = by_id.get(previous_product['gid'])
        if product is None:
            return None, '기존 상품 검색 결과 미확인: 전체 검색 스크립트로 재탐색 필요'
        detail = mrt.get_detail(product['gid'], product['url'])
        options = mrt.get_options(product['gid'], product['url'], date)
        if detail is None or options is None:
            return None, '상세/옵션 조회 실패: 기존 유지'
        if detail['meetingText'] != previous_product['meetingText']:
            return None, '집결지 변경: 전체 검색 스크립트로 위치 재판정 필요'
        # Preserve option-level location filtering for products with several venues.
        anchor = previous_product['locationEvidence'].split(': ')[-1]
        if any(any(k in o['optionName'] for k in ANCHORS) for o in options):
            options = [o for o in options if anchor in o['optionName'] and
                       not (anchor == '서울숲' and '북서울숲' in o['optionName'])]
        picked.append({**previous_product, **product, 'options': options,
                       'durationMin': detail['durationMin'], 'durationSource': detail['durationSource']})
    return {**previous, 'fetchedAt': datetime.now(timezone.utc).isoformat(), 'date': date,
            'queriesTried': queries, 'queriesFailed': [],
            'discoveryQueries': previous.get('discoveryQueries', previous['queriesTried']),
            'rejectedAsOf': previous.get('rejectedAsOf', previous['fetchedAt']),
            'picked': picked}, None


def save_snapshot(snapshot, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write('\n')
        temporary = Path(f.name)
    temporary.replace(path)


if __name__ == '__main__':
    snapshot, reason = refresh_snapshot() if '--refresh' in sys.argv else fetch_snapshot()
    if snapshot is None:
        print(reason, file=sys.stderr)
        sys.exit(1)
    # Refresh uses stdout mode; only its parent commits after the 10-second deadline.
    if '--stdout' in sys.argv:
        print(json.dumps(snapshot, ensure_ascii=False))
    else:
        save_snapshot(snapshot, ROOT / 'data/mrt_snapshot.json')
        print(f"스냅숏 저장: {snapshot['date']} · {len(snapshot['picked'])}개 상품")
        for p in snapshot['picked']:
            print(p['gid'], p['name'], p['options'])
