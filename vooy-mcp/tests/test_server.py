import asyncio
import json
from starlette.testclient import TestClient
from hapui import server
from hapui.store import STORE
from hapui.schema import HapuiError


def client():return TestClient(server.create_app(),base_url='http://127.0.0.1')

def test_health_host_and_bearer(monkeypatch):
    monkeypatch.setenv('HAPUI_TOKEN','test-secret')
    with client() as c:
        assert c.get('/healthz').json()['ok']
        # /healthz answers any Host (load-balancer probe); data routes still check it.
        assert c.get('/healthz',headers={'Host':'10.0.0.5:8080'}).status_code==200
        assert c.get('/b/unknown',headers={'Host':'evil.example'}).status_code==421
        assert c.get('/mcp').status_code==401
        assert c.get('/mcp',headers={'Authorization':'Bearer wrong'}).status_code==401
        assert c.post('/mcp',headers={'Authorization':'Bearer test-secret','Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}).status_code==200
        assert c.get('/b/unknown',headers={'Host':'localhost:8765.evil'}).status_code==421
        assert c.get('/b/unknown',headers={'Origin':'https://evil.example'}).status_code==403


def test_board_capability_expiration_and_security(result,monkeypatch):
    monkeypatch.setenv('HAPUI_TOKEN','test-secret')
    token=result['board_url'].split('/')[-1]
    with client() as c:
        page=c.get('/b/'+token)
        assert page.status_code==200
        assert 'frame-ancestors \'none\'' in page.headers['content-security-policy']
        assert page.headers['referrer-policy']=='no-referrer'
        assert page.headers['x-content-type-options']=='nosniff'
        assert '"mode":"web"' in page.text and '"token":"'+token+'"' in page.text
        assert c.get('/api/board/'+token).json()['problem_id']==result['problem_id']
        assert c.get('/api/board/'+result['problem_id']).status_code==404
        assert c.get('/b/unknown').status_code==404
        p=STORE.get(result['problem_id']);created=p.created;p.created-=STORE.ttl+1
        assert c.get('/api/board/'+token).status_code==404
        p.created=created;STORE.put(p)


def test_xss_boot_and_names(scenario):
    from hapui.planner import propose
    scenario['members'][0]['name']='<img src=x onerror=alert(1)>'
    r=propose(scenario);token=r['board_url'].split('/')[-1]
    with client() as c:
        html=c.get('/b/'+token).text
        assert '<img src=x' not in html
        assert '<img src=x' not in server.render(r)
    hostile={'mode':'web','token':'</script><img src=x onerror=alert(1)>'}
    escaped=server.boot_json(hostile)
    assert '</script>' not in escaped and '<img' not in escaped
    assert json.loads(escaped)==hostile


def test_board_adjust_and_invalid_json(result):
    token=result['board_url'].split('/')[-1]
    with client() as c:
        r=c.post('/api/board/'+token+'/adjust',json={'type':'weights','weights':{'민지':.5}})
        assert r.status_code==200 and r.json()['rev']>1
        assert c.post('/api/board/'+token+'/adjust',content='{',headers={'content-type':'application/json'}).status_code==400
        assert c.post('/api/board/'+token+'/adjust',json={'type':'delete_everything'}).json()['code']=='invalid_input'
        assert c.post('/api/board/unknown/adjust',json={'type':'undo'}).status_code==404
        assert c.post('/mcp',content='x'*65537).status_code==413


def test_rate_limits():
    with client() as c:
        responses=[c.get('/b/unknown').status_code for _ in range(61)]
        assert responses[-1]==429
    with client() as c:
        responses=[c.post('/api/board/unknown/adjust',json={'type':'undo'}).status_code for _ in range(21)]
        assert responses[-1]==429


def test_tool_contract_and_errors():
    async def run():
        tools=await server.mcp.list_tools()
        for t in tools:
            assert '예:' in t.description
            if t.name!='find_candidates':assert t.meta['ui']['resourceUri']==server.UI_URI
            for prop in t.input_schema['properties'].values():assert prop.get('description')
        r=await server.mcp.call_tool('propose_plans',{'members':[],'window':{'start':'13:00','end':'18:00'}})
        assert r.is_error and set(r.structured_content)=={'code','message','field','hint'}
        r=await server.mcp.call_tool('adjust_plan',{'problem_id':'none','action':{'type':'undo'}})
        assert r.is_error and r.structured_content['code']=='problem_not_found'
        resources=await server.mcp.list_resources()
        assert resources[0].mime_type=='text/html;profile=mcp-app'
    asyncio.run(run())


def test_stdio_protocol_survives_native_stdout(scenario,tmp_path):
    import sys
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters,stdio_client
    async def run():
        params=StdioServerParameters(command=sys.executable,args=['-m','hapui.server','--stdio'],cwd=server.ROOT)
        with (tmp_path/'stderr.log').open('w') as log:
            async with stdio_client(params,errlog=log) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=15) as session:
                    await session.initialize()
                    # Simultaneous quick responses must not disappear into CBC's /dev/null fd.
                    solve=asyncio.create_task(session.call_tool('propose_plans',scenario))
                    for _ in range(3):
                        await asyncio.sleep(.05)
                        assert len((await session.list_tools()).tools)==4
                    result=await solve
                    assert not result.is_error and result.structured_content['plans']
    asyncio.run(run())
