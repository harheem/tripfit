"""Messenger notifications must convey the result and retain quoted data."""
from copy import deepcopy
import pytest
from hapui.text import render


@pytest.fixture
def recorded(result):
    return deepcopy(result)


def test_notification_leads_with_people_and_preserves_body(recorded):
    lines=render(recorded).splitlines()
    assert lines[0]=='다들 OK인 코스 3안. "민지" 100, "지훈" 100, "서연" 100'
    assert len(lines)<=12
    assert lines[1].startswith('균형, "민지" 100%')
    assert '미반영: 없음, 실제 계산 / 샘플(성수)' in lines[-1]
    assert lines[-1].endswith('보드 '+recorded['board_url'])
    assert 'ms' not in lines[0] and '후보 순서' not in lines[0]


def test_notification_uses_default_and_quotes_untrusted_names(recorded):
    chosen=recorded['plans'][1]
    recorded['default_plan_id']=chosen['plan_id']
    chosen['per_person'][0].update(name='<지훈>"\n',pct=65)
    chosen['per_person'][1]['pct']=None
    first=render(recorded).splitlines()[0]
    assert first.startswith('함께 맞춘 코스 3안. ')
    assert '<' not in first and '\\u003c' in first and '\\"' in first
    assert ' 65' in first and '조건 없음' in first
    single=deepcopy(recorded);single['members']=single['members'][:1]
    assert render(single).splitlines()[0].startswith('한 사람 코스, ')
