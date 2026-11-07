"""Public chat HTTP boundary and its actual MCP resource/tool exchange."""
import json
import re
from starlette.testclient import TestClient
from hapui import server
from mcp.server.apps import client_supports_apps
from mcp.types import ClientCapabilities
from scripts.smoke_mcp import SCENARIO, IMPOSSIBLE


HEADERS={'Content-Type':'application/json','Accept':'application/json, text/event-stream',
         'Origin':'http://127.0.0.1','MCP-Protocol-Version':'2025-06-18'}
CAPABILITIES={'extensions':{'io.modelcontextprotocol/ui':{'mimeTypes':['text/html;profile=mcp-app']}}}


def test_chat_security_and_static_public_access(monkeypatch):
    monkeypatch.setenv('HAPUI_TOKEN','test-secret')
    with TestClient(server.create_app(),base_url='http://127.0.0.1') as c:
        page=c.get('/chat')
        assert page.status_code==200
        policy=page.headers['content-security-policy']
        nonce=re.search(r"script-src 'nonce-([^']+)'",policy)[1]
        for directive in ["default-src 'none'","connect-src 'self'","frame-src 'self'",
                          "frame-ancestors 'none'","base-uri 'none'","style-src 'unsafe-inline'","img-src 'self' data:"]:
            assert directive in policy
        assert page.headers['cache-control']=='no-store'
        assert page.headers['referrer-policy']=='no-referrer'
        assert page.headers['x-content-type-options']=='nosniff'
        assert page.headers['x-frame-options']=='DENY'
        assert page.text.count('<script ')==1 and f"nonce='{nonce}'" in page.text
        assert '__CSP_NONCE__' not in page.text
        assert c.get('/chat',headers={'Host':'evil.example'}).status_code==421
        assert c.get('/chat',headers={'Origin':'https://evil.example'}).status_code==403
        assert c.get('/preview').status_code==404
        assert c.get('/preview.html').status_code==404
        assert c.get('/chat').headers['content-security-policy']!=policy
        assert c.post('/mcp',headers=HEADERS,json={}).status_code==401


def test_chat_static_requests_keep_guard_limits(monkeypatch):
    monkeypatch.setattr(server,'RATE_PER_MIN',3)
    with TestClient(server.create_app(),base_url='http://127.0.0.1') as c:
        assert [c.get('/chat').status_code for _ in range(4)]==[200,200,200,429]


def test_chat_real_mcp_lifecycle(monkeypatch):
    monkeypatch.delenv('HAPUI_TOKEN',raising=False)
    # Exercise the exact SDK capability predicate used by the server.
    from types import SimpleNamespace
    ctx=SimpleNamespace(session=SimpleNamespace(client_capabilities=ClientCapabilities.model_validate(CAPABILITIES)))
    assert client_supports_apps(ctx)
    with TestClient(server.create_app(),base_url='http://127.0.0.1') as c:
        def rpc(method,params=None,notification=False):
            body={'jsonrpc':'2.0','method':method,'params':params or {}}
            if not notification:body['id']=1
            response=c.post('/mcp',headers=HEADERS,json=body)
            assert response.status_code in (200,202),response.text
            if notification:return
            envelope=response.json()
            assert 'error' not in envelope,envelope
            return envelope['result']
        initialized=rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':CAPABILITIES,'clientInfo':{'name':'chat-test','version':'1'}})
        assert initialized['protocolVersion']=='2025-06-18'
        rpc('notifications/initialized',notification=True)
        listed=rpc('tools/list')
        tool=next(t for t in listed['tools'] if t['name']=='propose_plans')
        uri=tool['_meta']['ui']['resourceUri']
        resource=rpc('resources/read',{'uri':uri})['contents'][0]
        assert resource['uri']==uri==server.UI_URI
        assert resource['mimeType']=='text/html;profile=mcp-app'
        assert '"mode":"app"' in resource['text']
        assert 'ui/initialize' in resource['text'] and '__CSP_NONCE__' not in resource['text']
        def call(name,args):
            result=rpc('tools/call',{'name':name,'arguments':args})
            assert not result.get('isError'),result
            assert result['content'][0]['text']
            return result['structuredContent']
        result=call('propose_plans',SCENARIO)
        assert result['status'] in ('ok','partial') and result['rev']==1
        adjusted=call('adjust_plan',{'problem_id':result['problem_id'],'action':{'type':'yield','name':'서연','text':'2만원 안으로'}})
        assert adjusted['rev']==2 and adjusted['problem_id']==result['problem_id']
        conflict=call('propose_plans',IMPOSSIBLE)
        assert conflict['status']=='infeasible' and conflict['concessions']
        explained=call('explain_infeasible',{'problem_id':conflict['problem_id']})
        assert explained['concessions']==conflict['concessions']
        resolved=call('adjust_plan',{'problem_id':conflict['problem_id'],'action':conflict['concessions'][0]['apply']})
        assert resolved['rev']==2 and resolved['status']!='infeasible'


def test_chat_smoke_arguments_and_source_hygiene():
    html=(server.ROOT/'ui/chat.html').read_text()
    for name,expected in [('SCENARIO',SCENARIO),('IMPOSSIBLE',IMPOSSIBLE)]:
        assert json.loads(re.search(r'const '+name+r'=(.*);',html)[1])==expected
    assert "fetch('/mcp'" in html and 'fixtures/' not in html
    assert 'allow-same-origin' not in html
    for file in ('ui/chat.html','ui/board.html','hapui/text.py'):
        source=(server.ROOT/file).read_text()
        assert not re.search('[\u00b7\u2014\u2013]',source),file
    for file in ('ui/chat.html','ui/board.html'):
        assert not re.search(r'innerHTML\s*=\s*[^\x27\x22`]|eval\(|new Function|on[a-z]+="',(server.ROOT/file).read_text()),file
