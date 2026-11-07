"""Published constants are the single source for normalization and scoring."""
from copy import deepcopy
from dataclasses import dataclass
from .schema import Candidate, Proposal, clean, minutes
from .engine.places_seongsu import PLACES
from .engine.tripfit_solver import Place, Pref, Request, place_quality

PUBLIC_DEFAULTS = {
    'strength': {'강': 1.0, '보통': 0.7, '약': 0.4},
    'walk_less_km': {'강': [1.5, 3.5], '보통': [2.5, 4.5], '약': [3.5, 6.0]},
    'walk_explicit_zero_extra_km': 2,
    'slow': {'full_stops': 3, 'zero_stops': 7},
    'rest_minutes': 50,
    'categories': {
        'exhibit': ['전시','미술관','갤러리','박물관','팝업'],
        'food': ['밥','점심','저녁','식당','맛집','식사'],
        'cafe': ['카페','커피','디저트','베이커리'],
        'shop': ['소품샵','편집샵','쇼핑','구경'],
        'alley': ['골목','거리','동네 구경'],
        'park': ['공원','산책','숲'],
        'activity': ['체험','공방','클래스','원데이'],
    },
    'walk': {'detour_factor': 1.3, 'meters_per_minute': 70},
    'stay_minutes': {'exhibit':60,'food':60,'cafe':50,'shop':30,'alley':30,'park':40,'activity':120},
    'alternatives': '균형(max-min) + 최소 만족도가 가장 낮은 사람 우선 + 말이 가장 많은 사람 우선(같은 안이면 합침)',
}


def category(value):
    value=clean(value).lower()
    for key, words in PUBLIC_DEFAULTS['categories'].items():
        if value==key or value in words: return key
    return None


def sample_places():
    places=deepcopy(PLACES)
    for p in places: p.tags += ['_any', 'place:'+p.id]
    return places


def candidates_to_places(raw, proposal, source='vooy'):
    places=[]; notes=[]; flags={}
    for i,c in enumerate(raw):
        try:
            if not isinstance(c,dict): raise ValueError()
            candidate=Candidate.model_validate(c)
        except (ValueError,TypeError):
            notes.append({'name':'','text':clean(c.get('name',''))[:200] if isinstance(c,dict) else '',
                          'reason':'좌표 없음 또는 후보 필드 형식·범위 오류로 제외'})
            continue
        c=candidate; cat=category(c.category) or 'other'; pid=f'{source}_{i}'
        p=Place(pid,clean(c.name)[:200],c.lat,c.lng,cat,c.stay_min or PUBLIC_DEFAULTS['stay_minutes'].get(cat,30),
                minutes(c.open) if c.open else 0, minutes(c.close) if c.close else 1440,
                price=c.price,source=('sample' if source=='vooy' and c.source=='sample' else source),group=clean(c.group)[:200] if c.group else None,
                fixed_start_min=minutes(c.fixed_start) if c.fixed_start else None,
                tags=['_any','place:'+pid],availability='unverified')
        if p.close_min<=p.open_min:
            notes.append({'name':'','text':p.name,'reason':'영업 종료가 시작보다 이른 후보 제외'});continue
        p.quality,p.quality_parts=place_quality(rating=c.rating,reviews=c.reviews)
        flags[pid]=[clean(f)[:200] for f in c.flags[:8]]
        if not c.open or not c.close: flags[pid].append('영업시간 미확인')
        if 'price' not in raw[i]: flags[pid].append('가격 미확인')
        places.append(p)
    if len(raw)>40:
        def rank(p):
            related=sum(1 for m in proposal.members for w in m.wants
                        if category(w.what or '')==p.category or (w.place_name or w.what or '\0') in p.name
                        or (w.kind=='eat_by' and p.category=='food') or (w.kind=='rest' and p.category=='cafe'))
            return related,p.quality
        places=sorted(places,key=rank,reverse=True)[:25]
        notes.append({'name':'','text':'','reason':'후보 40곳 초과: 말 관련도와 Q 순으로 25곳까지 줄였습니다'})
    return places,notes,flags


@dataclass
class Mapped:
    request: Request
    # Each original item stays visible, even if excluded from calculation.
    items: dict
    unmapped: list
    hard: list


def map_request(proposal: Proposal, places, state):
    names=[m.name for m in proposal.members]
    start=proposal.start_point
    if start: pt=(start.lat,start.lng)
    elif proposal.area in {'성수','성수동'}: pt=(37.5446,127.0557)
    else: pt=(places[0].lat,places[0].lng)
    end=proposal.end_point
    req=Request(names,pt,(end.lat,end.lng) if end else pt,minutes(proposal.window.start),minutes(proposal.window.end),
                prefs={n:[] for n in names},quality_weight=2.0,tag_min={'_any':1})
    req.weights=state.get('weights',{})
    req.must_include=list(state.get('added',[]));req.exclude=list(state.get('removed',[]))
    items={};unmapped=[];hard=[]
    yielded=state.get('yielded',set())
    for member in proposal.members:
        items[member.name]=[]
        for i,w in enumerate(member.wants):
            key=(member.name,i); weight=PUBLIC_DEFAULTS['strength'][w.strength]
            target=w.place_name or w.what or ('카페' if w.kind=='rest' else '')
            cat=category(target)
            matches=[p for p in places if target and (target==p.id or target in p.name)]
            # Prefer exact named targets; never silently choose among ambiguous places.
            exact=next((p for p in matches if target==p.name or target==p.id),None)
            if exact: matches=[exact]
            match={cat:1.0} if cat and not w.place_name else {'place:'+p.id:1.0 for p in matches}
            pref=None; reason=None; is_hard=False
            if w.kind in {'visit','rest','avoid'} and not match:
                reason='모르는 장소 종류·이름: 계산에서 제외'
            elif w.kind=='other': reason='장소 데이터로 확인할 수 없는 말'
            elif w.kind=='visit':
                pref=Pref(w.text,'visit',weight,w.text,match,full=w.count)
                is_hard=w.must
                if w.must and key not in yielded:
                    if cat and not w.place_name: req.category_min[cat]=max(req.category_min.get(cat,0),w.count)
                    elif len(matches)==1: req.must_include.append(matches[0].id)
                    else:
                        # Tag a named subset, allowing count without arbitrarily selecting a branch.
                        tag=f'want:{member.name}:{i}'
                        for p in matches:
                            if tag not in p.tags:p.tags.append(tag)
                        req.tag_min[tag]=w.count
            elif w.kind=='rest': pref=Pref(w.text,'dwell',weight,w.text,match,full=w.minutes)
            elif w.kind=='walk_less':
                full,zero=PUBLIC_DEFAULTS['walk_less_km'][w.strength]
                if w.max_km is not None: full,zero=w.max_km,w.max_km+PUBLIC_DEFAULTS['walk_explicit_zero_extra_km']
                pref=Pref(w.text,'walk',weight,w.text,full=full*1000,zero=zero*1000)
                is_hard=w.must
                if w.must and key not in yielded:req.max_walk_m=min(req.max_walk_m if req.max_walk_m is not None else float('inf'),full*1000)
            elif w.kind=='slow': pref=Pref(w.text,'stops',weight,w.text,full=w.max_stops,zero=max(7,w.max_stops+1))
            else:
                is_hard=True
                # Always-met hard items contribute a constant when any place is visited.
                pref=Pref(w.text,'visit',weight,w.text,{'_any':1},full=1)
                if key not in yielded:
                    if w.kind=='avoid':req.exclude += [p.id for p in places if p.category==cat or p in matches]
                    elif w.kind=='budget':req.budget=min(req.budget if req.budget is not None else 10**9,w.amount)
                    elif w.kind=='eat_by':req.eat_by=min(req.eat_by if req.eat_by is not None else 1440,minutes(w.time))
                    elif w.kind=='leave_by':req.deadline_min=min(req.deadline_min,minutes(w.time))
            if reason:
                unmapped.append({'name':member.name,'text':w.text,'reason':reason})
            if is_hard and key not in yielded and not reason:hard.append(key)
            items[member.name].append({'want':w,'pref':pref,'key':key,'unmapped':bool(reason),'yielded':key in yielded})
            if pref and key not in yielded and not reason:req.prefs[member.name].append(pref)
    # A category request count is shared, not summed across members. Distinct
    # named restaurant visits within one member's wishes also allow multiple meals.
    food_limit=1
    for member in proposal.members:
        named=set()
        for item in items[member.name]:
            w=item['want']
            if item['yielded'] or item['unmapped'] or w.kind!='visit':continue
            target=w.place_name or w.what or ''
            if category(target)=='food' and not w.place_name:
                food_limit=max(food_limit,w.count)
            else:
                matches=[p for p in places if target and (target==p.id or target in p.name)]
                if matches and all(p.category=='food' for p in matches):
                    named.add(target)
                    food_limit=max(food_limit,w.count)
        food_limit=max(food_limit,len(named))
    req.category_max['food']=food_limit
    return Mapped(req,items,unmapped,hard)
