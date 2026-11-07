"""Bounded solver orchestration, transactional adjustments, and honest diagnosis."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import math
import os
import threading
import time
from mip import BINARY, xsum
from . import mrt
from .mapping import candidates_to_places, map_request, sample_places
from .schema import Action, HapuiError, Proposal, Result, clock, minutes
from .store import Problem, STORE
from .engine.tripfit_solver import (TripFitSolver, Plan, Stop, checklist_of, checklist_pct,
    estimate_walk_matrix, haversine_m, _quiet_native_stdout)

SOLVER_LOCK=threading.Lock()
COLORS=['pink','sky','peach','butter','mint','lilac','pink','sky']


class OpenRouteSolver(TripFitSolver):
    """Keep vendored math intact; adapt terminal arcs and soft saturation for PRD semantics."""
    def __init__(self,places,open_end,**kwargs):
        super().__init__(places,**kwargs);self.open_end=open_end

    def _matrices(self,req,places):
        dist,mins=estimate_walk_matrix([req.start]+[(p.lat,p.lng) for p in places]+[req.end])
        if self.open_end:
            for row in dist:row[-1]=0
            for row in mins:row[-1]=0
        return dist,mins

    @staticmethod
    def _checklist_expr(m,prefs,places,P,y,walk_m):
        # The original f>=0 imposes an accidental ceiling on soft walk/stops.
        # This adapter implements max(0,min(1,line)), with the same published slopes.
        if not prefs:return xsum([])
        total=sum(p.weight for p in prefs);terms=[]
        for pref in prefs:
            if pref.kind not in {'walk','stops'}:
                terms.append(TripFitSolver._checklist_expr(m,[pref],places,P,y,walk_m)*pref.weight/100)
                continue
            f=m.add_var(lb=0,ub=1);over=m.add_var(var_type=BINARY)
            amount=walk_m if pref.kind=='walk' else xsum(y[k] for k in P)
            span=pref.zero-pref.full
            max_amount=100800 if pref.kind=='walk' else len(places)
            big=max(1,(max_amount-pref.zero)/span+1)
            m += f <= (pref.zero-amount)/span+big*over
            m += f <= 1-over
            terms.append(pref.weight*f)
        return xsum(terms)*(100/total) if total else xsum([])


def find_candidates(area='성수',kinds=None,date=None):
    from .schema import clean
    area=clean(area)[:100] or '성수'
    result=mrt.search(area,(kinds or ['체험'])[0],date)
    live=mrt.extract_candidates(result,area) if result is not None else []
    candidates=[]
    if area in {'성수','성수동'}:
        for p in sample_places():
            candidates.append({'id':p.id,'name':p.name,'lat':p.lat,'lng':p.lng,'category':p.category,
                'open':clock(p.open_min),'close':clock(p.close_min),'stay_min':p.duration_min,'price':p.price,
                'source':'sample','fixed_start':clock(p.fixed_start_min) if p.fixed_start_min is not None else None,
                'group':p.group,'flags':['샘플 데이터','예약가능 미확인']})
    candidates.extend(live)
    return {'v':1,'candidates':candidates,'source_status':{'places':('샘플(성수) + MRT 실호출' if live else '샘플(성수)') if area in {'성수','성수동'} else ('MRT 실호출' if live else '없음'),
            'mrt':'실호출' if result is not None else '실패'}}


def _problem(raw):
    proposal=Proposal.model_validate(raw)
    labels={'solver':'실제 계산','places':'샘플(성수)','mrt':'미사용','walk':'직선거리×1.3 추정'}
    notes=[];flags={}
    if proposal.candidates is not None:
        # A caller cannot promote their supplied candidates to MRT verified data.
        places,notes,flags=candidates_to_places(proposal.candidates,proposal,'vooy')
        labels['places']=' + '.join(label for source,label in [('sample','샘플'),('vooy','vooy 제공')] if any(p.source==source for p in places)) or 'vooy 제공'
    elif proposal.area in {'성수','성수동'}:
        places=sample_places()
    else:
        found=find_candidates(proposal.area,date=proposal.date)
        places,notes,flags=candidates_to_places(found['candidates'],proposal,'mrt')
        labels.update(found['source_status'])
        if places and not proposal.start_point:
            notes.append({'name':'','text':'','reason':'출발점 미제공: 첫 후보 좌표를 출발점으로 사용했습니다'})
    return Problem(proposal,places,labels,notes,flags)


def _error(code,message,field=None):
    raise HapuiError(code,message,field)


def propose(raw):
    started=time.monotonic();p=_problem(raw)
    result=_compute(p,started+9.5)
    p.result=result;STORE.put(p)
    return deepcopy(result)


def explain(problem_id):
    p=STORE.get(problem_id)
    return deepcopy(p.result)


def adjust(problem_id,action):
    started=time.monotonic();a=Action.model_validate(action);p=STORE.get(problem_id)
    if not p.lock.acquire(timeout=8):
        raise HapuiError('busy','같은 코스를 계산 중입니다',hint='잠시 뒤 다시 시도해 주세요')
    try:
        oldstate=deepcopy(p.state);oldstack=deepcopy(p.undo);oldresult=p.result;oldrev=p.rev
        if a.type=='undo':
            if not p.undo:_error('nothing_to_undo','되돌릴 변경이 없습니다','action.type')
            p.state=p.undo.pop()
        else:
            nextstate=deepcopy(p.state)
            if a.type=='yield':
                for name,text in [(a.name,a.text)]+[(x.name,x.text) for x in a.also]:
                    member=next((m for m in p.proposal.members if m.name==name),None)
                    if member is None:_error('member_not_found','해당 이름을 찾을 수 없습니다','action.name')
                    exact=[i for i,w in enumerate(member.wants) if w.text==text]
                    matches=exact or [i for i,w in enumerate(member.wants) if text in w.text]
                    if len(matches)!=1:_error('want_not_found','이번엔 뺄 말이 없거나 여러 말과 겹칩니다. 더 길게 적어 주세요','action.text')
                    nextstate['yielded'].add((name,matches[0]))
            elif a.type=='weights':
                if any(n not in {m.name for m in p.proposal.members} for n in a.weights):_error('member_not_found','weights의 이름을 확인해 주세요','action.weights')
                nextstate['weights'].update(a.weights)
            else:
                exact=[q for q in p.places if a.place_name in {q.id,q.name}]
                matches=exact or [q for q in p.places if a.place_name in q.name]
                if len(matches)!=1:_error('place_not_found','후보 장소가 없거나 이름이 여러 곳과 겹칩니다','action.place_name')
                pid=matches[0].id; dest='added' if a.type=='add' else 'removed';opposite='removed' if dest=='added' else 'added'
                if pid not in nextstate[dest]:nextstate[dest].append(pid)
                nextstate[opposite]=[x for x in nextstate[opposite] if x!=pid]
            p.checkpoint();p.state=nextstate
        try:
            p.rev+=1;new=_compute(p,started+9.5)
            if oldresult['plans'] and new['plans']:
                before,after=oldresult['plans'][0],new['plans'][0]
                oldids={s['place_id'] for s in before['stops']};newids={s['place_id'] for s in after['stops']}
                oldpct={v['name']:v['pct'] for v in before['per_person']}
                new['diff']={'added':[s['name'] for s in after['stops'] if s['place_id'] not in oldids],
                             'dropped':[s['name'] for s in before['stops'] if s['place_id'] not in newids],
                             'pct_delta':{v['name']:round(v['pct']-oldpct[v['name']],1) if v['pct'] is not None and oldpct[v['name']] is not None else None for v in after['per_person']}}
            else:new['diff']={'added':[],'dropped':[],'pct_delta':{}}
            p.result=new
            return deepcopy(new)
        except Exception:
            p.state=oldstate;p.undo=oldstack;p.rev=oldrev;p.result=oldresult
            raise
    finally:p.lock.release()


def _plan_result(p,mapped,plan,pid,label,approx=False):
    per=[]
    for m in p.proposal.members:
        items=[]
        for item in mapped.items[m.name]:
            pref=item['pref'];w=item['want']
            fill=checklist_of([pref],plan.stops,plan.total_walk_m)[0]['fulfilled'] if pref else 0
            state='unmapped' if item['unmapped'] else 'yielded' if item['yielded'] else 'met' if fill>=1 else 'missed' if fill<=0 else 'partial'
            weight=0 if state in {'unmapped','yielded'} else pref.weight
            items.append({'text':w.text,'fill':fill,'weight':weight,'status':state})
        total=sum(x['weight'] for x in items)
        pct=round(100*sum(x['weight']*x['fill'] for x in items)/total,1) if total else None
        per.append({'name':m.name,'pct':pct,'items':items})
    return {'plan_id':pid,'label':label,'stops':[{
        'place_id':s.place.id,'name':s.place.name,'category':s.place.category,'arrive':clock(s.start_min),
        'leave':clock(s.end_min),'walk_m':round(s.walk_m_from_prev),'price':s.place.price,'source':s.place.source,
        'flags':list(dict.fromkeys(p.place_flags.get(s.place.id,[])+(['샘플 데이터'] if s.place.source=='sample' else [])+
            (['예약가능 미확인'] if s.place.availability=='unverified' else [])))} for s in plan.stops],
        'per_person':per,'min_pct':min((x['pct'] for x in per if x['pct'] is not None),default=100),'walk_km':round(plan.total_walk_m/1000,3),
        'cost_per_person':sum(s.place.price for s in plan.stops),'end':clock(plan.finish_min),'flags':['근사해'] if approx else []}


def _valid(plan,req):
    if not plan or not plan.stops or plan.finish_min>req.deadline_min:return False
    ids=plan.ids();ps=[s.place for s in plan.stops]
    if req.max_walk_m is not None and plan.total_walk_m>req.max_walk_m:return False
    if req.budget is not None and sum(p.price for p in ps)>req.budget:return False
    if req.eat_by is not None and not any(s.place.category=='food' and s.start_min<req.eat_by for s in plan.stops):return False
    if any(x in req.exclude for x in ids):return False
    if any(x not in ids and not any(p.group==x for p in ps) for x in req.must_include):return False
    if any(sum(p.category==c for p in ps)>n for c,n in req.category_max.items()):return False
    if any(sum(p.category==c for p in ps)<n for c,n in req.category_min.items()):return False
    if any(sum(t in p.tags for p in ps)<n for t,n in req.tag_min.items()):return False
    if any(not any(s.place.id==pid and s.start_min==v for s in plan.stops) for pid,v in req.locks.items()):return False
    return True


def _route(seq,req,open_end):
    stops=[];point=req.start;now=req.start_min;walk=0
    groups=set()
    for p in seq:
        group=p.group or p.id
        if group in groups or p.id in req.exclude:return None
        groups.add(group)
        d=haversine_m(point,(p.lat,p.lng))*1.3;arrive=now+d/70
        start=max(arrive,p.open_min,p.fixed_start_min or 0,req.locks.get(p.id,0))
        fixed=req.locks.get(p.id,p.fixed_start_min)
        if fixed is not None and start>fixed+1e-6:return None
        if start+p.duration_min>min(p.close_min,req.deadline_min):return None
        now=start+p.duration_min;walk+=d
        if req.max_walk_m is not None and walk>req.max_walk_m:return None
        stops.append(Stop(p,round(arrive),round(start),round(now),round(d),round(d/70,1)));point=(p.lat,p.lng)
    if not open_end:
        d=haversine_m(point,req.end)*1.3;walk+=d;now+=d/70
    if now>req.deadline_min or (req.budget is not None and sum(p.price for p in seq)>req.budget):return None
    if req.max_walk_m is not None and walk>req.max_walk_m:return None
    checklist={n:checklist_of(req.prefs.get(n,[]),stops,walk) for n in req.people}
    pct={n:checklist_pct(x) for n,x in checklist.items()}
    return Plan('근사',stops,round(walk),round(walk/70,1),round(now),pct,pct,checklist)


def _heuristic(places,req,open_end,deadline):
    """Greedy beam of insertions; only fully hard-valid routes can escape."""
    beam=[[]];best=None;bestscore=-float('inf')
    for _ in range(min(12,len(places))):
        options=[];seen=set()
        for seq in beam:
            for p in places:
                if time.monotonic()>deadline:return best
                if p in seq or p.id in req.exclude:continue
                # Append and also try insertion before the first stop (fixed slots).
                for route in (seq+[p],[p]+seq) if seq else ([p],):
                    key=tuple(q.id for q in route)
                    if key in seen:continue
                    seen.add(key);plan=_route(route,req,open_end)
                    if plan is None:continue
                    satisfaction=list(plan.satisfaction.values())
                    score=(min(satisfaction) if satisfaction else 0)*req.fairness_weight+sum(
                        req.weights.get(n,1)*v for n,v in plan.satisfaction.items())+sum(q.quality for q in route)*2-plan.total_walk_m/1000
                    hard= sum(q.id in req.must_include or q.group in req.must_include for q in route)
                    hard+=sum(min(n,sum(q.category==c for q in route)) for c,n in req.category_min.items())
                    hard+=sum(min(n,sum(t in q.tags for q in route)) for t,n in req.tag_min.items())
                    hard+=int(req.eat_by is not None and any(s.place.category=='food' and s.start_min<req.eat_by for s in plan.stops))
                    options.append((hard*100000+score,route))
                    if _valid(plan,req) and score>bestscore:best,bestscore=plan,score
        options.sort(key=lambda x:x[0],reverse=True);beam=[route for _,route in options[:16]]
        if not beam:break
    return best


def _solve(p,mapped,deadline,limit=3,weights=None,fair=True):
    req=deepcopy(mapped.request)
    # Members with no scored items (or a zero slider) do not collapse max-min to zero.
    req.people=[n for n in req.people if req.prefs.get(n) and p.state['weights'].get(n,1)>0]
    req.fairness_weight=100 if fair and req.people else 0
    req.weights=weights if weights is not None else {n:0.01*p.state['weights'].get(n,1) for n in req.people}
    req.sat_scale={n:1/max(p.state['weights'].get(n,1),0.001) for n in req.people}
    if req.deadline_min<=req.start_min:return None,False,'INFEASIBLE'
    remaining=deadline-time.monotonic()
    if remaining<0.08:return None,False,'TIMEOUT'
    solver=OpenRouteSolver(p.places,p.proposal.end_point is None,time_limit_s=min(3,limit,max(.02,remaining-.08)))
    # Lock is held by _compute, including model construction and native output teardown.
    with _quiet_native_stdout():
        plan,status=solver._solve(req,'plan')
    if _valid(plan,req):return plan,False,status
    fallback=_heuristic(p.places,req,p.proposal.end_point is None,min(deadline,time.monotonic()+.15))
    return fallback,bool(fallback),status


def _diagnose(p,mapped,deadline):
    concessions=[];initial=p.state
    try:
        for count in (1,2):
            for combo in combinations(mapped.hard,count):
                if time.monotonic()>deadline-.12:break
                p.state=deepcopy(initial);p.state['yielded'].update(combo)
                variant=map_request(p.proposal,p.places,p.state)
                plan,approx,_=_solve(p,variant,deadline,limit=.35)
                if plan:
                    score=_plan_result(p,variant,plan,'balanced','균형',approx)['min_pct']
                    wants=[(name,p.proposal.members[[m.name for m in p.proposal.members].index(name)].wants[i].text) for name,i in combo]
                    action={'type':'yield','name':wants[0][0],'text':wants[0][1]}
                    if len(wants)>1:action['also']=[{'name':wants[1][0],'text':wants[1][1]}]
                    concessions.append({'id':f'c{len(concessions)+1}','who':', '.join(dict.fromkeys(n for n,t in wants)),
                        'give_up':[f"{n}의 '{t[3:-3] + ' 이내' if t.startswith('걷기 ') and t.endswith(' 하드') else t}'를 빼면" for n,t in wants],'then_min_pct':score,'apply':action})
                    if len(concessions)>=4:break
            if concessions or time.monotonic()>deadline-.12:break
    finally:p.state=initial
    return concessions


def _compute(p,deadline):
    started=time.monotonic();proposal=p.proposal
    base=os.environ.get('HAPUI_PUBLIC_URL') or 'http://127.0.0.1:'+os.environ.get('HAPUI_PORT','8765')
    output={'v':1,'status':'ok','problem_id':p.problem_id,'rev':p.rev,'board_url':base.rstrip('/')+'/b/'+p.board_token,
        'area':proposal.area,'window':proposal.window.model_dump(),'members':[{'name':m.name,'color':COLORS[i]} for i,m in enumerate(proposal.members)],
        'data_labels':p.source_status,'warnings':[n.model_dump() for n in proposal.warnings],'unmapped':list(p.notes),
        'search_space':sum(math.perm(len(p.places),k) for k in range(1,min(len(p.places),6)+1)),
        'plans':[],'concessions':[]}
    if not p.places:
        output['data_labels']={**p.source_status,'solver':'미실행','places':'없음'}
        output.update(status='need_candidates',message='vooy에서 장소를 찾아 좌표가 있는 candidates로 넘겨 주세요')
        return Result.model_validate(output).model_dump()
    wait=min(8,max(0,deadline-time.monotonic()-.2))
    if not SOLVER_LOCK.acquire(timeout=wait):raise HapuiError('busy','다른 코스를 계산 중입니다',hint='잠시 뒤 다시 시도해 주세요')
    try:
        mapped=map_request(proposal,p.places,p.state)
        output['unmapped']+=mapped.unmapped
        if not any(mapped.request.prefs.values()):
            output['warnings'].append({'name':'','text':'','reason':'조건으로 바꿀 수 있는 말이 없었습니다. 장소 점수 Q로 계산합니다'})
        plan,approx,status=_solve(p,mapped,deadline,limit=min(3,max(.05,(deadline-time.monotonic())*.42)))
        if plan:
            balanced=_plan_result(p,mapped,plan,'balanced','균형',approx);output['plans'].append(balanced)
            scored=[v for v in balanced['per_person'] if v['pct'] is not None]
            worst=min(scored,key=lambda x:x['pct'])['name'] if scored else proposal.members[0].name
            most=max(proposal.members,key=lambda m:len(m.wants)).name
            targets=list(dict.fromkeys([worst,most]))
            seen={tuple(plan.ids())}
            for n in targets:
                alt,ap,_=_solve(p,mapped,deadline,limit=min(3,max(.05,(deadline-time.monotonic())/max(1,len(targets)))),weights={n:1},fair=False)
                if alt and tuple(alt.ids()) not in seen:
                    seen.add(tuple(alt.ids()));output['plans'].append(_plan_result(p,mapped,alt,'favor:'+n,n+' 우선',ap))
            output['status']='partial' if output['unmapped'] or output['warnings'] else 'ok'
            if any(x['flags'] for x in output['plans']):output['flags']=['근사해']
        else:
            if status not in {'INFEASIBLE','MISSING_MUST','MISSING_LOCK','INT_INFEASIBLE'}:
                raise HapuiError('solver_timeout','제한 시간 안에 조건을 지키는 코스를 찾지 못했습니다',hint='후보나 필수 조건을 줄여 다시 시도해 주세요')
            output['status']='infeasible';output['concessions']=_diagnose(p,mapped,deadline)
            if not output['concessions']:output['message']='시간 안에 검증된 선택지를 찾지 못했습니다. 필수 조건이나 시간창을 조정해 주세요'
        output['solve_ms']=round((time.monotonic()-started)*1000)
        return Result.model_validate(output).model_dump()
    finally:SOLVER_LOCK.release()
