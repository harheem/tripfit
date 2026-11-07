"""Bounded JSON-RPC client. No URLs supplied by users or remote content are opened."""
import asyncio
import json
import time
import httpx
from .schema import clean

MRT_URL='https://mcp-servers.myrealtrip.com/mcp'
MAX_BYTES=1024*1024


def search(area,kind='체험',date=None):
    try:
        return asyncio.run(_search(area,kind,date))
    except (httpx.HTTPError,ValueError,TypeError,UnicodeError,TimeoutError):
        return None


async def _search(area,kind,date):
    query='서울 '+clean(area)[:100]+' '+clean(kind)[:100]
    payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'searchTnas','arguments':{'query':query}}}
    # A wall-clock deadline also covers slow trickles of otherwise timely chunks.
    async with asyncio.timeout(5):
        async with httpx.AsyncClient(timeout=5,follow_redirects=False,trust_env=False) as client:
            async with client.stream('POST',MRT_URL,json=payload,headers={'Accept':'application/json, text/event-stream','Accept-Encoding':'identity'}) as response:
                response.raise_for_status()
                size=int(response.headers.get('content-length','0'))
                if size>MAX_BYTES:return None
                if response.headers.get('content-encoding','identity') not in ('identity',''):return None
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body)+len(chunk)>MAX_BYTES:return None
                    body.extend(chunk)
                    if 'text/event-stream' in response.headers.get('content-type',''):
                        parsed=_parse_sse(body.decode('utf-8',errors='replace'))
                        if parsed is not None:return None if isinstance(parsed,dict) and parsed.get('isError') else parsed
                text=body.decode('utf-8')
                parsed=_parse_sse(text+'\n\n') if text.lstrip().startswith(('data:', 'event:', ':')) else json.loads(text)
                if not isinstance(parsed,dict) or parsed.get('error') or parsed.get('isError'):return None
                result=parsed.get('result',parsed)
                return None if isinstance(result,dict) and result.get('isError') else result


def _parse_sse(text):
    for event in text.replace('\r\n','\n').split('\n\n')[:-1]:
        value='\n'.join(line[5:].lstrip() for line in event.splitlines() if line.startswith('data:'))
        try:
            obj=json.loads(value)
            if isinstance(obj,dict) and obj.get('error'):return None
            if isinstance(obj,dict) and 'result' in obj:return obj['result']
        except ValueError:pass
    return None


def extract_candidates(result,area):
    """Accept known JSON envelopes; missing coordinates stay missing (never geocode by guess)."""
    out=[]
    def walk(value,depth=0):
        if depth>10:return
        if isinstance(value,list):
            for item in value:walk(item,depth+1)
        elif isinstance(value,dict):
            title=value.get('name') or value.get('title')
            if title and clean(area) in (str(title)+' '+str(value.get('address',''))):
                coords=value.get('location') if isinstance(value.get('location'),dict) else {}
                out.append({'name':clean(title)[:200], 'lat':value.get('lat',value.get('latitude',coords.get('lat'))),
                            'lng':value.get('lng',value.get('longitude',coords.get('lng'))),
                            'category':'activity','source':'mrt','price':value.get('price',0),
                            'flags':['영업시간 미확인','예약가능 미확인']+([] if 'price' in value else ['가격 미확인'])})
            for k,v in value.items():
                if k=='text' and isinstance(v,str):
                    try:walk(json.loads(v),depth+1)
                    except ValueError:pass
                elif isinstance(v,(dict,list)):walk(v,depth+1)
    walk(result)
    return out[:40]
