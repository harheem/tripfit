"""Public v1 contract and forgiving, bounded messenger input normalization."""
from __future__ import annotations
import re
import unicodedata
from datetime import date as Date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


def clean(value: Any) -> str:
    return ''.join(c for c in str('' if value is None else value) if unicodedata.category(c) not in {'Cc', 'Cf', 'Cs'}).strip()


def minutes(value: Any) -> int:
    s = clean(value).lower().replace(' ', '')
    match = re.fullmatch(r'(?:(오전|오후))?(\d{1,2})(?::(\d{2})|시(?:(\d{1,2})분?)?)?(am|pm)?', s)
    if not match:
        raise ValueError('시간은 15:00, 15시, 오후 3시, 3pm처럼 입력해 주세요')
    ko, h, m, km, en = match.groups(); h, m = int(h), int(m or km or 0)
    if ko or en:
        if not 1 <= h <= 12:
            raise ValueError('오전·오후 시간은 1~12시로 입력해 주세요')
        h = h % 12 + (12 if ko == '오후' or en == 'pm' else 0)
    if m > 59 or h > 24 or (h == 24 and m):
        raise ValueError('시간은 00:00~24:00 범위로 입력해 주세요')
    return h * 60 + m


def clock(n: int) -> str:
    return f'{n // 60:02}:{n % 60:02}'


def money(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('금액은 원 단위 숫자 또는 2만원처럼 입력해 주세요')
    s = clean(value).replace(',', '').replace(' ', '').removesuffix('원')
    try:
        n = float(s[:-1]) * 10000 if s.endswith('만') else float(s)
        if not 0 <= n <= 100_000_000 or not n.is_integer():
            raise ValueError()
        return int(n)
    except (ValueError, OverflowError):
        raise ValueError('금액은 0~1억원, 예: 20000 또는 2만원') from None


class Model(BaseModel):
    model_config = ConfigDict(extra='ignore', str_strip_whitespace=True, allow_inf_nan=False)


class Window(Model):
    start: str = Field(description='시작 시각. 예: 13:00, 오후 1시')
    end: str = Field(description='종료 시각. 예: 18:00, 6pm. 시작보다 늦어야 함')

    @field_validator('start', 'end', mode='before')
    @classmethod
    def normalize_time(cls, v):
        return clock(minutes(v))

    @model_validator(mode='after')
    def ordered(self):
        if minutes(self.end) <= minutes(self.start):
            raise ValueError('window.end는 window.start보다 늦어야 합니다. 예: 13:00~18:00')
        return self


class Point(Model):
    name: str = Field(default='출발점', description='기준 지점 이름. 예: 성수역')
    lat: float = Field(ge=-90, le=90, description='위도. 예: 37.5446')
    lng: float = Field(ge=-180, le=180, description='경도. 예: 127.0557')


KINDS = {'visit', 'avoid', 'walk_less', 'rest', 'slow', 'eat_by', 'leave_by', 'budget', 'other'}


class Want(Model):
    text: str = Field(default='', description='사용자가 한 말. 예: 전시 하나는 꼭. 최대 200자')
    kind: str = Field(default='other', description='visit/avoid/walk_less/rest/slow/eat_by/leave_by/budget/other. 예: visit. 모르는 값은 other')
    what: str | None = Field(default=None, description='장소 종류 또는 이름. 예: 전시, 디뮤지엄')
    place_name: str | None = Field(default=None, description='특정 장소명. 예: 디뮤지엄 기획전')
    strength: str = Field(default='보통', description='강/보통/약 또는 strong/normal/weak. 생략·없음은 보통')
    must: bool = Field(default=False, description='필수 방문·걷기 상한이면 true. 예: 전시 꼭 → true')
    count: int = Field(default=1, ge=1, le=40, description='방문 희망 수. 예: 골목 2곳 → 2')
    max_km: float | None = Field(default=None, ge=0, le=100, description='걷기 기준 또는 필수 상한 km. 예: 1.5')
    minutes: int = Field(default=50, ge=1, le=720, description='휴식 희망 분. 예: 50')
    max_stops: int = Field(default=3, ge=1, le=40, description='느긋하게 방문할 곳 수. 예: 3')
    time: str | None = Field(default=None, description='식사 또는 종료 시한. 예: 15:00, 오후 3시, 3pm')
    amount: int | None = Field(default=None, ge=0, description='1인 예산 원. 예: 20000, 2만원, 2만')

    @field_validator('kind', mode='before')
    @classmethod
    def normalize_kind(cls, v):
        return v if isinstance(v, str) and v in KINDS else 'other'

    @field_validator('strength', mode='before')
    @classmethod
    def normalize_strength(cls, v):
        return {'강':'강','strong':'강','약':'약','weak':'약','보통':'보통','normal':'보통'}.get(clean(v).lower(), '보통')

    @field_validator('time', mode='before')
    @classmethod
    def normalize_time(cls, v):
        return None if v is None else clock(minutes(v))

    @field_validator('amount', mode='before')
    @classmethod
    def normalize_amount(cls, v):
        return None if v is None else money(v)

    @field_validator('text', 'what', 'place_name', mode='before')
    @classmethod
    def normalize_text(cls, v):
        return clean(v)[:200] if v is not None else None

    @model_validator(mode='after')
    def required_detail(self):
        if self.kind in {'eat_by', 'leave_by'} and self.time is None:
            raise ValueError('time이 필요합니다. 예: 15:00')
        if self.kind == 'budget' and self.amount is None:
            raise ValueError('amount가 필요합니다. 예: 20000')
        return self


class Member(Model):
    name: str = Field(default='', description='사람 이름. 예: 민지. 빈 이름·중복은 자동 보정, 20자 이내')
    wants: list[Want] = Field(default_factory=list, description='그 사람이 한 말 목록. 예: [{text: 전시 꼭, kind: visit, what: 전시, must: true}]. 최대 8개')


class Candidate(Model):
    name: str = Field(description='장소 이름. 예: 성수 국밥집(샘플)')
    lat: float = Field(ge=-90, le=90, description='위도. 예: 37.5441. 좌표 없는 후보는 제외')
    lng: float = Field(ge=-180, le=180, description='경도. 예: 127.0558')
    category: str = Field(default='other', description='장소 종류. 예: 카페, 식당, exhibit')
    open: str | None = Field(default=None, description='여는 시각. 예: 11:00. 생략하면 영업시간 미확인')
    close: str | None = Field(default=None, description='닫는 시각. 예: 21:00. 생략하면 영업시간 미확인')
    stay_min: int | None = Field(default=None, ge=1, le=720, description='체류 분. 예: 50. 생략하면 공개 기본값')
    price: int = Field(default=0, ge=0, description='1인 가격 원. 예: 8000. 미제공은 0으로 계산하며 미확인 표시')
    rating: float | None = Field(default=None, ge=0, le=5, description='평점 0~5. 예: 4.5')
    reviews: int = Field(default=0, ge=0, le=100000000, description='리뷰 수. 예: 120')
    source: Literal['sample','mrt','vooy'] = Field(default='vooy', description='데이터 출처. 예: vooy. 서버가 실제 수집 경로로 지정')
    id: str | None = Field(default=None, description='후보 식별자. 예: food_soup')
    fixed_start: str | None = Field(default=None, description='고정 시작 시각. 예: 14:00. 예약 확인을 의미하지 않음')
    group: str | None = Field(default=None, description='동일 상품 시간대 그룹. 예: leather')
    flags: list[str] = Field(default_factory=list, description='불확실한 데이터 표시. 예: 가격 미확인')

    @field_validator('open','close','fixed_start',mode='before')
    @classmethod
    def normalize_time(cls,v):
        return None if v is None else clock(minutes(v))

    @field_validator('price',mode='before')
    @classmethod
    def normalize_price(cls,v):
        return money(v)


class Note(Model):
    name: str = ''
    text: str = ''
    reason: str


class Proposal(Model):
    area: str = Field(default='성수', description='동네. 예: 성수. 다른 동네는 candidates 권장')
    date: str = Field(default_factory=lambda: Date.today().isoformat(), description='나들이 날짜. 예: 2026-11-08. 생략하면 오늘')
    window: Window = Field(description='활동 시간창. 예: {start: 13:00, end: 18:00}. 1~12시간')
    start_point: Point | None = Field(default=None, description='출발 지점. 예: {name: 성수역, lat: 37.5446, lng: 127.0557}')
    end_point: Point | None = Field(default=None, description='종료 지점. 예: 서울숲역 좌표. 생략하면 마지막 장소에서 종료')
    members: list[Member] = Field(min_length=1, description='참여자 1~8명. 예: [{name: 민지, wants: [...]}]')
    candidates: list[dict[str, Any]] | None = Field(default=None, description='vooy가 찾은 후보. 예: [{name: 카페, lat: 37.54, lng: 127.05, category: 카페, price: 8000}]. 40곳 초과는 관련도와 Q로 25곳 선택', json_schema_extra={'items': Candidate.model_json_schema()})
    warnings: list[Note] = Field(default_factory=list, exclude=True, description='서버 정규화 경고. 입력할 필요 없음. 예: 인원 8명으로 자름')

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, data):
        if not isinstance(data, dict):
            return data
        d = dict(data); notes = []
        def note(reason, name='', text=''):
            notes.append(dict(name=name, text=text, reason=reason))
        for key in ('area','date'):
            if key in d:
                d[key] = clean(d[key])[:100]
        members=d.get('members')
        if isinstance(members,list):
            if len(members)>8: note('인원을 8명으로 잘랐습니다')
            out=[]; used=set()
            for i, raw in enumerate(members[:8]):
                if not isinstance(raw,dict):
                    out.append(raw); continue
                m=dict(raw); base=clean(m.get('name'))[:20] or f'친구{i+1}'; name=base; count=2
                while name in used:
                    suffix=f'({count})'; name=base[:20-len(suffix)]+suffix; count+=1
                if name != raw.get('name'): note('이름을 정규화했습니다', name)
                used.add(name); m['name']=name; wants=m.get('wants',[])
                if isinstance(wants,list):
                    if len(wants)>8: note('말을 8개로 잘랐습니다',name)
                    normalized=[]
                    for w in wants[:8]:
                        if isinstance(w,dict):
                            w=dict(w)
                            for k in ('text','what','place_name'):
                                if k in w and w[k] is not None:
                                    s=clean(w[k])
                                    if len(s)>200: note(f'{k}를 200자로 잘랐습니다',name)
                                    w[k]=s[:200]
                        normalized.append(w)
                    m['wants']=normalized
                out.append(m)
            d['members']=out
        w=d.get('window')
        if isinstance(w,dict) and 'start' in w and 'end' in w:
            try:
                a,b=minutes(w['start']),minutes(w['end'])
                if b>a and (b-a<60 or b-a>720):
                    b=min(1440,a+max(60,min(720,b-a)))
                    a=min(a,b-60)
                    d['window']={'start':clock(a),'end':clock(b)}
                    note('시간창을 1~12시간 범위로 보정했습니다')
            except ValueError: pass
        d['warnings']=notes
        return d


class YieldItem(Model):
    name: str = Field(description='양보할 사람. 예: 서연')
    text: str = Field(description='양보할 말의 전부 또는 일부. 예: 2만원')


class Action(Model):
    type: Literal['yield','weights','add','remove','undo'] = Field(description='변경 종류. 예: yield')
    name: str | None = Field(default=None, description='양보할 사람의 정규화된 이름. 예: 서연')
    text: str | None = Field(default=None, description='양보할 말. 부분 일치 허용. 예: 2만원')
    weights: dict[str,float] | None = Field(default=None, description='사람별 중요도 0~1. 예: {민지: 0.5, 지훈: 1.0}')
    place_name: str | None = Field(default=None, description='추가 또는 제외할 후보 장소명. 예: 디뮤지엄')
    rev: int | None = Field(default=None, description='클라이언트가 본 버전. 예: 2. 최신 상태에 적용')
    also: list[YieldItem] = Field(default_factory=list, max_length=1, description='서버가 제안한 2개 양보의 두 번째 항목. 예: [{name: 민지, text: 공방}]')

    @field_validator('name','text','place_name',mode='before')
    @classmethod
    def normalize_text(cls,v):
        return clean(v)[:200] if v is not None else None

    @model_validator(mode='after')
    def details(self):
        if self.type=='yield' and (not self.name or not self.text): raise ValueError('yield에는 name과 text가 필요합니다')
        if self.type in {'add','remove'} and not self.place_name: raise ValueError('장소 이름 place_name이 필요합니다')
        if self.type=='weights' and (not self.weights or any(not 0<=x<=1 for x in self.weights.values())): raise ValueError('weights는 사람 이름별 0~1 값이어야 합니다')
        if self.also and self.type!='yield': raise ValueError('also는 양보 조합에서만 사용합니다')
        return self


class Item(Model):
    text: str
    fill: float = Field(ge=0,le=1)
    weight: float = Field(ge=0,le=1)
    status: Literal['met','partial','missed','yielded','unmapped']


class PersonResult(Model):
    name: str
    pct: float | None = Field(default=None,ge=0,le=100)
    items: list[Item]


class StopResult(Model):
    place_id: str
    name: str
    category: str
    arrive: str
    leave: str
    walk_m: int
    price: int
    source: Literal['sample','mrt','vooy']
    flags: list[str] = Field(default_factory=list)


class PlanResult(Model):
    plan_id: str
    label: str
    stops: list[StopResult]
    per_person: list[PersonResult]
    min_pct: float
    walk_km: float
    cost_per_person: int
    end: str
    flags: list[str] = Field(default_factory=list)


class Concession(Model):
    id: str
    who: str
    give_up: list[str]
    then_min_pct: float
    apply: Action


class Result(Model):
    v: Literal[1] = 1
    status: Literal['ok','partial','infeasible','need_candidates']
    problem_id: str
    rev: int = 1
    board_url: str | None = None
    area: str
    window: Window
    members: list[dict[str,str]]
    search_space: int = 0
    solve_ms: int = 0
    plans: list[PlanResult] = Field(default_factory=list)
    default_plan_id: str = 'balanced'
    diff: dict[str,Any] | None = None
    concessions: list[Concession] = Field(default_factory=list)
    unmapped: list[Note] = Field(default_factory=list)
    warnings: list[Note] = Field(default_factory=list)
    data_labels: dict[str,str]
    flags: list[str] = Field(default_factory=list)
    message: str | None = None


class Error(Model):
    code: str
    message: str
    field: str | None = None
    hint: str


class HapuiError(Exception):
    def __init__(self, code, message, field=None, hint='입력을 확인하고 다시 시도해 주세요'):
        self.error=Error(code=code,message=message,field=field,hint=hint)
        super().__init__(code)


def error_from(exc):
    if isinstance(exc,HapuiError): return exc.error.model_dump()
    if isinstance(exc,ValidationError):
        e=exc.errors(include_input=False,include_url=False)[0]
        field='.'.join(map(str,e['loc'])) or 'input'
        if field=='window' and 'window.end' in e['msg']:field='window.end'
        msg=e['msg']
        if msg.startswith('Value error, '): msg=msg[13:]
        if not re.search('[가-힣]',msg): msg='필수 값이 없거나 입력 형식·범위가 맞지 않습니다'
        return Error(code='invalid_input',message=msg,field=field,hint='필드 설명의 예시에 맞춰 주세요. 시간창은 시작보다 늦게 끝나야 합니다').model_dump()
    return Error(code='internal_error',message='계산을 마치지 못했습니다',hint='잠시 뒤 다시 시도해 주세요').model_dump()
