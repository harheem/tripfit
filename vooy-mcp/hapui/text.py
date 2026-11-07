"""At most twelve messenger lines; untrusted strings are quoted data."""
import json
from .schema import clean


def quote(value):
    # Quotes and angle brackets stay escaped; no remote name becomes markup or a command.
    return json.dumps(clean(value),ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e')


def render(result):
    if 'code' in result:
        return f"{result['message']} [{result['code']}]\n필드: {result.get('field') or '요청'}\n{result['hint']}"
    if 'candidates' in result:
        return f"후보 {len(result['candidates'])}곳\n출처: {result['source_status'].get('places','')} · MRT {result['source_status']['mrt']}"
    lines=[]
    if len(result['members'])==1:lines.append('한 사람 코스')
    if result['status']=='infeasible':lines.append('모든 필수 조건을 함께 지키는 코스가 없습니다.')
    elif result['status']=='need_candidates':lines.append(result.get('message') or '좌표가 있는 후보가 필요합니다.')
    else:lines.append(f"{len(result['plans'])}안 · 계산 {result['solve_ms']}ms · 후보 순서 조합 약 {result['search_space']:,}개")
    for p in result['plans'][:3]:
        label='균형' if p['plan_id']=='balanced' else quote(p['plan_id'].removeprefix('favor:'))+' 우선'
        people=' · '.join(quote(v['name'])+ (f" {v['pct']:g}%" if v['pct'] is not None else " 조건 없음") for v in p['per_person'])
        route=' → '.join(quote(s['name'])+'('+s['arrive']+')' for s in p['stops'])
        lines.append(f'{label} · {people} · {route}')
    for c in result.get('concessions',[])[:4]:
        lines.append(f"양보: {quote(c['who'])} · {', '.join(quote(t) for t in c['give_up'])} → 최소 {c['then_min_pct']:g}%")
    if result.get('flags'):lines.append('계산 표시: '+', '.join(result['flags']))
    if result.get('warnings'):lines.append('안내: '+' / '.join(quote(n['reason']) for n in result['warnings'][:2]))
    unmapped=result.get('unmapped',[])
    labels=result['data_labels']
    tail='미반영: '+(' / '.join(quote(n.get('name',''))+' '+quote(n.get('text',''))+' '+quote(n['reason']) for n in unmapped[:2]) if unmapped else '없음')
    tail+=f" · {labels['solver']} / {labels['places']} / MRT {labels['mrt']} / {labels['walk']}"
    if result.get('board_url'):tail+=' · 보드 '+result['board_url']
    return '\n'.join(lines[:11]+[tail])
