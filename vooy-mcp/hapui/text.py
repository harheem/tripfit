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
        return f"후보 {len(result['candidates'])}곳\n출처: {result['source_status'].get('places','')}, MRT {result['source_status']['mrt']}"
    lines=[]
    if result['status']=='infeasible':lines.append('이대로는 안 돼요. 하나만 빼면 돼요')
    elif result['status']=='need_candidates':lines.append(result.get('message') or '좌표가 있는 후보가 필요합니다.')
    else:
        plan=next((p for p in result['plans'] if p['plan_id']==result['default_plan_id']),result['plans'][0])
        scored=[p for p in plan['per_person'] if p['pct'] is not None]
        title='다들 OK인 코스' if scored and min(p['pct'] for p in scored)>=90 else '함께 맞춘 코스'
        people=', '.join(quote(p['name'])+(f" {p['pct']:g}" if p['pct'] is not None else ' 조건 없음') for p in plan['per_person'])
        prefix='한 사람 코스, ' if len(result['members'])==1 else ''
        lines.append(f"{prefix}{title} {len(result['plans'])}안. {people}")
    if result['plans']:
        removed=[(p['name'],i['text']) for p in plan['per_person'] for i in p['items'] if i['status']=='yielded']
        if removed:
            names=list(dict.fromkeys(n for n,t in removed))
            lines[0]=', '.join(quote(n)[1:-1] for n in names)+' 덕분에 다들 OK' if scored and min(p['pct'] for p in scored)>=90 else lines[0]
            lines.append('이번엔 뺐어요: '+', '.join(quote(t) for n,t in removed))
            lines.append('다음엔 '+', '.join(quote(n)[1:-1] for n in names)+'이 먼저 골라요')
    for p in result['plans'][:3]:
        label='균형' if p['plan_id']=='balanced' else quote(p['plan_id'].removeprefix('favor:'))+' 우선'
        people=', '.join(quote(v['name'])+ (f" {v['pct']:g}%" if v['pct'] is not None else " 조건 없음") for v in p['per_person'])
        route=' → '.join(quote(s['name'])+'('+s['arrive']+')' for s in p['stops'])
        lines.append(f'{label}, {people}, {route}')
    for c in result.get('concessions',[])[:4]:
        lines.append(f"{', '.join(quote(t)[1:-1] for t in c['give_up'])} 다들 {c['then_min_pct']:g}%")
    if result.get('flags'):lines.append('계산 표시: '+', '.join(result['flags']))
    if result.get('warnings'):lines.append('안내: '+' / '.join(quote(n['reason']) for n in result['warnings'][:2]))
    unmapped=result.get('unmapped',[])
    labels=result['data_labels']
    tail='미반영: '+(' / '.join(quote(n.get('name',''))+' '+quote(n.get('text',''))+' '+quote(n['reason']) for n in unmapped[:2]) if unmapped else '없음')
    tail+=f", {labels['solver']} / {labels['places']} / MRT {labels['mrt']} / {labels['walk']}"
    if result.get('board_url'):tail+=', 보드 '+result['board_url']
    return '\n'.join(lines[:11]+[tail])
