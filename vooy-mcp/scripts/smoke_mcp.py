#!/usr/bin/env python3
"""Official mcp==2.3 client. Exercises only the supplied MCP URL, no MRT calls."""
import asyncio
from copy import deepcopy
import json
import os
import sys
import time
from pathlib import Path
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SCENARIO={
    'area':'성수','window':{'start':'13:00','end':'18:00'},
    'members':[
        {'name':'민지','wants':[{'text':'전시 하나는 꼭','kind':'visit','what':'전시','must':True,'strength':'강'}]},
        {'name':'지훈','wants':[{'text':'많이 걷기 싫어','kind':'walk_less','strength':'강'}, {'text':'3시 전엔 밥','kind':'eat_by','time':'15:00'}]},
        {'name':'서연','wants':[{'text':'카페에서 좀 쉬고 싶어','kind':'rest'}, {'text':'2만원 안으로','kind':'budget','amount':20000}]},
    ]}
IMPOSSIBLE={'area':'성수','window':{'start':'13:00','end':'18:00'},'members':[
    {'name':'민지','wants':[{'text':'디뮤지엄 꼭','kind':'visit','what':'디뮤지엄','must':True},
                          {'text':'공방 14시 꼭','kind':'visit','place_name':'가죽공방 원데이클래스 14:00','must':True}]},
    {'name':'지훈','wants':[{'text':'걷기 1km 하드','kind':'walk_less','max_km':1,'must':True}]}]}

async def smoke(url,transport=None):
    headers={}
    if os.environ.get('HAPUI_TOKEN'):headers['Authorization']='Bearer '+os.environ['HAPUI_TOKEN']
    records=[]
    async with httpx2.AsyncClient(headers=headers,timeout=20,follow_redirects=True,transport=transport) as http:
        async with streamable_http_client(url,http_client=http) as streams:
            async with ClientSession(streams[0],streams[1],read_timeout_seconds=20) as session:
                t=time.perf_counter();await session.initialize();print(f'initialize {(time.perf_counter()-t)*1000:.0f}ms')
                t=time.perf_counter();listed=await session.list_tools();print('tools/list',','.join(x.name for x in listed.tools),f'{(time.perf_counter()-t)*1000:.0f}ms')
                assert len(listed.tools)==4
                async def call(label,name,args,error=False):
                    t=time.perf_counter();result=await session.call_tool(name,args);ms=round((time.perf_counter()-t)*1000)
                    data=result.structured_content
                    print(f'[{label}] {ms}ms isError={result.is_error}')
                    for block in result.content:
                        if block.type=='text':print('\n'.join(block.text.splitlines()[:3]));break
                    assert bool(result.is_error)==error,(label,data)
                    assert isinstance(data,dict)
                    if error:assert all(k in data for k in ('code','message','field','hint'))
                    else:assert data['v']==1
                    records.append({'step':label,'ms':ms,'result':data,
                                    'content':[block.text for block in result.content if block.type=='text']})
                    return data
                result=await call('3인 시나리오','propose_plans',SCENARIO)
                assert result['status'] in {'ok','partial'} and 2<=len(result['plans'])<=3
                changed=await call('서연 예산 양보','adjust_plan',{'problem_id':result['problem_id'],'action':{'type':'yield','name':'서연','text':'2만원'}})
                assert changed['rev']==2
                impossible=await call('불가능 시나리오','propose_plans',IMPOSSIBLE)
                assert impossible['status']=='infeasible' and impossible['concessions']
                weird=[]
                p=deepcopy(SCENARIO);p['members']=[];weird.append(('빈 members',p,True))
                p=deepcopy(SCENARIO);p['members'][0]['name']='민지😊';p['members'][1]['name']='민지😊';weird.append(('중복·이모지',p,False))
                p=deepcopy(SCENARIO);p['members'][0]['wants'][0]['kind']='순간이동';weird.append(('모르는 kind',p,False))
                p=deepcopy(SCENARIO);p['window']={'start':'18:00','end':'13:00'};weird.append(('뒤집힌 창',p,True))
                p=deepcopy(SCENARIO);p['members'][0]['wants'][0]['text']='가'*1000;weird.append(('1000자 말',p,False))
                p=deepcopy(SCENARIO);p['members'][0]['name']='<img src=x onerror=alert(1)>';weird.append(('XSS 이름',p,False))
                for label,p,error in weird:await call(label,'propose_plans',p,error)
    # Explicitly requested local verification artifact; no user production records are persisted.
    Path('scripts/smoke_result.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'PASS: {len(records)} tool calls')

async def in_process():
    # Diagnostic fallback when this execution sandbox forbids listening sockets.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from hapui.server import create_app
    app=create_app()
    async with app.router.lifespan_context(app):
        transport=httpx2.ASGITransport(app=app)
        await smoke('http://127.0.0.1:8765/mcp',transport)
        async with httpx2.AsyncClient(transport=transport) as client:
            response=await client.get('http://127.0.0.1:8765/healthz')
            print('ASGI /healthz:',response.status_code,response.json())

if __name__=='__main__':
    if '--in-process' in sys.argv:asyncio.run(in_process())
    else:asyncio.run(smoke(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765/mcp'))
