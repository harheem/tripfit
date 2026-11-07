import json
from hapui import mrt,planner

class Response:
    def __init__(self,body,headers=None,status=200):self.body=body;self.headers=headers or {};self.status=status
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    def raise_for_status(self):
        if self.status>=400:
            import httpx
            raise httpx.HTTPError('failure')
    async def aiter_bytes(self):yield self.body

class Client:
    def __init__(self,response,calls):self.response=response;self.calls=calls
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    def stream(self,method,url,**kwargs):self.calls.append((method,url,kwargs));return self.response

def mock(monkeypatch,response):
    calls=[];monkeypatch.setattr(mrt.httpx,'AsyncClient',lambda **kw:Client(response,calls));return calls

def test_json_fixed_url(monkeypatch):
    calls=mock(monkeypatch,Response(json.dumps({'result':{'items':[]}}).encode()))
    assert mrt.search('http://localhost/private')=={'items':[]}
    assert calls[0][1]==mrt.MRT_URL
    assert calls[0][2]['json']['params']['name']=='searchTnas'


def test_sse_and_area_filter(monkeypatch):
    result={'items':[{'title':'성수 공방','lat':37.54,'lng':127.05},{'title':'홍대 공방','lat':37.55,'lng':126.9}]}
    mock(monkeypatch,Response(('event: message\ndata: '+json.dumps({'result':result})+'\n\n').encode(),{'content-type':'text/event-stream'}))
    data=mrt.search('성수');candidates=mrt.extract_candidates(data,'성수')
    assert len(candidates)==1 and candidates[0]['source']=='mrt'


def test_size_and_failure(monkeypatch):
    for response in [Response(b'x'*(1024*1024+1)),Response(b'{}',{'content-length':str(1024*1024+1)}),Response(b'no json'),Response(b'{}',status=500)]:
        mock(monkeypatch,response);assert mrt.search('성수') is None


def test_find_failure_uses_sample(monkeypatch):
    monkeypatch.setattr(mrt,'search',lambda *a:None)
    r=planner.find_candidates('성수')
    assert r['source_status']['mrt']=='실패'
    assert len(r['candidates'])==16 and all(c['source']=='sample' for c in r['candidates'])
