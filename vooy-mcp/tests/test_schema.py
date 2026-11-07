import pytest
from pydantic import ValidationError
from hapui.schema import Proposal,Want,minutes,money,error_from,Action
from hapui.mapping import map_request,sample_places,candidates_to_places

@pytest.mark.parametrize('value',["15:00","15시","오후 3시","3pm"])
def test_times(value):assert minutes(value)==900

@pytest.mark.parametrize('value',[20000,'2만원','2만','20,000원'])
def test_money(value):assert money(value)==20000

@pytest.mark.parametrize('value,expected',[('강','강'),('strong','강'),('normal','보통'),('weak','약'),('없음','보통'),(None,'보통')])
def test_strength(value,expected):assert Want(strength=value).strength==expected

@pytest.mark.parametrize('value',['25:00','오후 15시','15:70',{},-3])
def test_bad_times(value):
    with pytest.raises(ValueError):minutes(value)

def test_limits_and_control_cleanup(scenario):
    scenario['members']=[{'name':'\u202e\x00'+('민'*25),'wants':[{'text':'말'*1000,'kind':'other'}]*10}]*10
    scenario['window']={'start':'01:00','end':'23:00'}
    p=Proposal.model_validate(scenario)
    assert len(p.members)==8 and all(len(m.wants)==8 and len(m.name)<=20 for m in p.members)
    assert len({m.name for m in p.members})==8
    assert all(len(w.text)==200 for m in p.members for w in m.wants)
    assert p.window.end=='13:00' and p.warnings
    assert all('\u202e' not in m.name and '\x00' not in m.name for m in p.members)

def test_short_window_and_blank_names(scenario):
    scenario['window']={'start':'23:50','end':'24:00'}
    scenario['members']=[{'name':' '},{'name':'😀'},{'name':'😀'}]
    p=Proposal.model_validate(scenario)
    assert p.window.start=='23:00' and p.window.end=='24:00'
    assert [m.name for m in p.members]==['친구1','😀','😀(2)']

def test_bad_window_and_empty_members(scenario):
    for key,value in [('members',[]),('window',{'start':'18:00','end':'13:00'})]:
        bad={**scenario,key:value}
        with pytest.raises(ValidationError) as exc:Proposal.model_validate(bad)
        error=error_from(exc.value)
        assert set(error)=={'code','message','field','hint'} and error['code']=='invalid_input'
        assert key in error['field']

def test_other_downgrade(scenario):
    scenario['members'][0]['wants']=[{'text':'날자','kind':'순간이동'}, {'text':'우주','kind':'visit','what':'달나라'}]
    p=Proposal.model_validate(scenario);mapped=map_request(p,sample_places(),{})
    assert p.members[0].wants[0].kind=='other'
    assert len(mapped.unmapped)==2 and not mapped.request.prefs['민지']

def test_candidates_cap_and_missing_coords(scenario):
    p=Proposal.model_validate(scenario)
    raw=[{'name':f'카페{i}','lat':37.54,'lng':127.05,'category':'카페','rating':4.5} for i in range(45)]+[{'name':'좌표없음'}]
    places,notes,flags=candidates_to_places(raw,p)
    assert len(places)==25 and any('25곳' in n['reason'] for n in notes)
    assert any('좌표 없음' in n['reason'] for n in notes)
    assert all('영업시간 미확인' in fs for fs in flags.values())
    assert all(p.source=='vooy' for p in places)

def test_invalid_weights():
    with pytest.raises(ValidationError):Action(type='weights',weights={'민지':2})
