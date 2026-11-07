from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import time
import pytest
from hapui import planner
from hapui.schema import HapuiError,Proposal,Result
from hapui.mapping import map_request,sample_places
from hapui.store import STORE,Store,Problem
from hapui.text import render
from scripts.smoke_mcp import IMPOSSIBLE


def test_three_plans_and_hard_constraints(result):
    assert len(result['plans'])==3
    Result.model_validate(result)
    assert result['plans'][0]['plan_id']=='balanced'
    for plan in result['plans']:
        assert plan['cost_per_person']<=20000
        assert any(s['category']=='food' and s['arrive']<'15:00' for s in plan['stops'])
        assert any(s['category']=='exhibit' for s in plan['stops'])
        assert plan['end']<='18:00'
        assert all(s['source']=='sample' for s in plan['stops'])
        assert len(plan['per_person'])==3
    assert len(render(result).splitlines())<=12


def test_infeasible_concessions_apply():
    r=planner.propose(IMPOSSIBLE)
    assert r['status']=='infeasible' and r['concessions']
    assert all(c['who'] and c['apply']['type']=='yield' for c in r['concessions'])
    r2=planner.adjust(r['problem_id'],r['concessions'][0]['apply'])
    assert r2['status'] in {'ok','partial'} and r2['plans']


def test_adjust_revision_and_undo(scenario):
    r=planner.propose(scenario);pid=r['problem_id'];p=STORE.get(pid)
    r2=planner.adjust(pid,{'type':'yield','name':'서연','text':'2만원','rev':-1})
    assert r2['rev']==2 and r2['diff'] is not None and ('서연',1) in p.state['yielded']
    assert any(i['status']=='yielded' and i['weight']==0 for i in r2['plans'][0]['per_person'][2]['items'])
    r3=planner.adjust(pid,{'type':'undo'})
    assert r3['rev']==3 and not p.state['yielded']
    with pytest.raises(HapuiError):planner.adjust(pid,{'type':'yield','name':'없는 사람','text':'말'})
    assert p.rev==3


def test_undo_stack_limited(scenario):
    p=Problem(Proposal.model_validate(scenario),[],{})
    for _ in range(15):p.checkpoint()
    assert len(p.undo)==10


def test_ttl_lru_and_separate_tokens(scenario):
    now=[0];store=Store(ttl=10,capacity=2,clock=lambda:now[0])
    def make():return store.put(Problem(Proposal.model_validate(scenario),[],{}))
    a,b=make(),make()
    assert a.problem_id!=a.board_token and len(a.problem_id)>=32 and len(a.board_token)>=32
    store.get(a.problem_id);c=make()
    with pytest.raises(HapuiError):store.by_token(b.board_token)
    now[0]=11
    with pytest.raises(HapuiError):store.by_token(a.board_token)
    with pytest.raises(HapuiError):store.get(c.problem_id)


def test_concurrent_ten_proposals(scenario):
    def run(_):
        try:return planner.propose(deepcopy(scenario))['status']
        except HapuiError as exc:return exc.error.code
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(run,range(10)))
    assert len(results)==10 and set(results)<={'ok','partial','busy'}


def test_busy_lock(scenario):
    p=planner._problem(scenario)
    planner.SOLVER_LOCK.acquire()
    try:
        with pytest.raises(HapuiError) as error:planner._compute(p,time.monotonic()+.25)
        assert error.value.error.code=='busy'
    finally:planner.SOLVER_LOCK.release()


def test_fallback_is_flagged_and_feasible(scenario,monkeypatch):
    monkeypatch.setattr(planner.OpenRouteSolver,'_solve',lambda *a:(None,'NO_SOLUTION_FOUND'))
    r=planner.propose(scenario)
    assert '근사해' in r['flags'] and r['plans']
    for plan in r['plans']:
        assert plan['cost_per_person']<=20000
        assert any(s['category']=='exhibit' for s in plan['stops'])
        assert any(s['category']=='food' and s['arrive']<'15:00' for s in plan['stops'])


def test_unknown_area_needs_candidates(scenario,monkeypatch):
    monkeypatch.setattr(planner.mrt,'search',lambda *a:None)
    scenario['area']='없는 동네'
    r=planner.propose(scenario)
    assert r['status']=='need_candidates' and r['data_labels']['mrt']=='실패'


def test_all_other_uses_quality(scenario):
    scenario['members']=[{'name':'나','wants':[{'text':'재밌게','kind':'other'}]}]
    r=planner.propose(scenario)
    assert r['plans'] and r['status']=='partial'
    assert '한 사람 코스' in render(r)


def test_specific_avoid_and_budget_zero(scenario):
    scenario['members']=[{'name':'나','wants':[{'text':'돈 안 쓰기','kind':'budget','amount':0},
        {'text':'대림창고 빼기','kind':'avoid','place_name':'대림창고 전시'}]}]
    r=planner.propose(scenario)
    for plan in r['plans']:
        assert plan['cost_per_person']==0 and all(s['place_id']!='exh_daelim' for s in plan['stops'])


def test_pair_concessions_are_atomic(monkeypatch,scenario):
    # Two independent impossible must-visit category constraints require a pair.
    scenario['window']={'start':'13:00','end':'14:00'}
    scenario['members']=[{'name':'민지','wants':[{'text':'전시 꼭','kind':'visit','what':'전시','must':True}]},
                         {'name':'지훈','wants':[{'text':'공방 꼭','kind':'visit','what':'공방','must':True}]}]
    scenario['candidates']=[{'name':'카페','lat':37.5446,'lng':127.0557,'category':'카페','stay_min':20}]
    r=planner.propose(scenario)
    assert r['status']=='infeasible' and r['concessions']
    c=r['concessions'][0]
    assert c['apply']['also']
    r2=planner.adjust(r['problem_id'],c['apply'])
    assert r2['plans'] and r2['rev']==2


def test_soft_walk_zero_does_not_become_hard(scenario):
    scenario['members']=[{'name':'나','wants':[{'text':'적게 걷기','kind':'walk_less','strength':'강'},
        {'text':'먼 전시 꼭','kind':'visit','what':'전시','must':True}]}]
    scenario['start_point']={'name':'출발','lat':37.5446,'lng':127.0557}
    scenario['candidates']=[{'name':'먼 전시','lat':37.58,'lng':127.0557,'category':'전시','stay_min':30}]
    r=planner.propose(scenario)
    assert r['plans'] and r['plans'][0]['walk_km']>3.5
    assert r['plans'][0]['per_person'][0]['items'][0]['fill']==0


def test_end_point_adds_return_walk(scenario):
    scenario['members']=[{'name':'나','wants':[{'text':'전시','kind':'visit','what':'전시','must':True}]}]
    scenario['candidates']=[{'name':'전시','lat':37.55,'lng':127.0557,'category':'전시','stay_min':30}]
    a=planner.propose(scenario)
    scenario['end_point']={'lat':37.5446,'lng':127.0557}
    b=planner.propose(scenario)
    assert b['plans'][0]['walk_km']>a['plans'][0]['walk_km']
    assert b['plans'][0]['end']>a['plans'][0]['end']


def test_supplied_samples_cannot_become_live(scenario):
    scenario['candidates']=[{'name':'샘플','lat':37.54,'lng':127.05,'category':'카페','source':'sample'}]
    scenario['members']=[{'name':'나','wants':[]}]
    r=planner.propose(scenario)
    assert r['plans'][0]['stops'][0]['source']=='sample'
    assert '샘플' in r['data_labels']['places']


def test_restaurant_cap_and_explicit_multiple(scenario,monkeypatch):
    scenario['members']=[{'name':'나','wants':[{'text':'밥','kind':'visit','what':'식당'}]}]
    scenario['candidates']=[{'name':f'식당{i}','lat':37.5446,'lng':127.0557,
        'category':'식당','stay_min':30} for i in range(3)]
    r=planner.propose(scenario)
    assert r['plans'] and all(sum(s['category']=='food' for s in p['stops'])<=1 for p in r['plans'])
    scenario['members'][0]['wants'][0].update(count=2,must=True)
    r=planner.propose(scenario)
    assert r['plans'] and all(sum(s['category']=='food' for s in p['stops'])==2 for p in r['plans'])
    # Approximate routes must obey the same upper bound.
    monkeypatch.setattr(planner.OpenRouteSolver,'_solve',lambda *a:(None,'NO_SOLUTION_FOUND'))
    scenario['members'][0]['wants'][0].update(count=1,must=False)
    r=planner.propose(scenario)
    assert r['plans'] and all(len(p['stops'])==1 for p in r['plans'])


def test_yield_only_condition_is_unscored(scenario):
    scenario['members'][2]['wants']=[{'text':'2만원 안으로','kind':'budget','amount':20000}]
    r=planner.propose(scenario)
    changed=planner.adjust(r['problem_id'],{'type':'yield','name':'서연','text':'2만원'})
    Result.model_validate(changed)
    for p in changed['plans']:
        person=p['per_person'][2]
        assert person['pct'] is None and person['items'][0]['status']=='yielded'
        assert p['min_pct']==min(v['pct'] for v in p['per_person'] if v['pct'] is not None)
    assert '"서연" 조건 없음' in render(changed)
    assert changed['diff']['pct_delta']['서연'] is None
    restored=planner.adjust(r['problem_id'],{'type':'undo'})
    assert all(p['per_person'][2]['pct']==100 for p in restored['plans'])


def test_yield_budget_keeps_rest_scored(scenario):
    r=planner.propose(scenario)
    changed=planner.adjust(r['problem_id'],{'type':'yield','name':'서연','text':'2만원'})
    for p in changed['plans']:
        person=p['per_person'][2]
        rest=next(i for i in person['items'] if i['status']!='yielded')
        assert person['pct']==round(rest['fill']*100,1)
