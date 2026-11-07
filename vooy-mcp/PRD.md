# 합의저울 PRD v0.1 — vooy 트랙 (OBA.RUN 2nd, 2026-11-07)

> 단톡방에서 각자 한 줄씩 말하면, 다들 OK인 나들이 코스 3안과 누가 얼마나 양보하는지를 계산해 주는 vooy용 원격 MCP 서버

- 배경·조사·대안 비교: `IDEAS.md`. 이 문서는 무엇을 어떻게 만들지 정한다
- 제출: 별도 프로젝트, Vooy 트랙. GitHub URL 필수. 코드 프리즈 17:00
- 구현: Codex 위임(`codex/NN_*.md`), 이 세션은 리뷰
- 원칙: **LLM은 숫자를 만들지 않는다.** vooy의 LLM은 말을 조건으로 옮기고, 숫자는 솔버와 공개 기본값표에서 나온다
- 전제: **실제 사람들이 아무렇게나 쓴다.** 이상한 입력, 겹치는 이름, 모르는 동네, 동시 호출, 악의적 문자열이 들어온다. 어떤 입력에도 서버가 죽거나 빈 답을 내면 안 된다

---

## 1. 범위

| 넣는다 | 뺀다 |
|---|---|
| 친구 2~8명의 반나절~하루 나들이 코스(장소 여러 곳 × 순서 × 시간) | 회식 장소 1곳 투표, 날짜 투표, 정산 |
| 각자의 말 → 체크리스트 → 3안(균형안 + 가장 덜 챙겨진 사람 우선안 + 가장 많이 말한 사람 우선안) | 실제 예약·결제(vooy 기존 연동의 일) |
| 양보 반영 재계산, 불가능할 때 최소 양보 선택지 | 길찾기 API 실호출(직선거리 × 1.3 보정으로 도보 추정) |
| 후보: vooy가 넘긴 장소 / 성수 샘플 / 마이리얼트립 체험 실호출 | 다른 동네 샘플 데이터 |
| 텍스트 결과(본편) + MCP App 위젯 + 같은 화면의 웹 링크 | 로그인, 사용자 계정, 영구 저장 |

## 2. 사용 흐름

1. 단톡방: "민지: 전시 하나는 꼭" / "지훈: 많이 걷기 싫어, 3시 전엔 밥" / "서연: 카페에서 쉬고 싶어, 2만원 안으로" / "@vooy 성수 오후 코스 짜줘"
2. vooy LLM이 `propose_plans` 호출(레시피 지침이 언제·어떻게 부를지 알려 줌)
3. 서버: 입력 정규화 → 후보 확보 → 솔버 → 3안 또는(불가능하면) 양보 선택지
4. 결과: `content` 텍스트(메신저에 그대로 붙여도 읽힘) + `structuredContent`(위젯·보드용) + 보드 링크
5. "서연: 예산 좀 넘어도 돼" → vooy가 `adjust_plan(yield)` / 위젯·보드에서 양보 버튼이나 저울 → 같은 함수
6. "균형안으로" → vooy가 자기 연동으로 예약 단계(우리 범위 밖)

## 3. MCP 도구 계약

도구는 4개로 줄인다(vooy 도구 검색 대응). 모든 도구 설명에 한국어 예문 5개 + 영어 한 줄.

### 3.1 `propose_plans` (model + app)

입력:

```jsonc
{
  "area": "성수",                       // 선택. candidates가 없을 때 샘플·실호출 범위
  "date": "2026-11-08",                 // 선택. MRT 옵션 조회용. 없으면 오늘
  "window": {"start": "13:00", "end": "18:00"},   // 필수. HH:MM, 길이 1~12시간
  "start_point": {"name": "성수역", "lat": 37.5446, "lng": 127.0557},  // 선택. 없으면 area 기본값
  "end_point": null,                    // 선택. 없으면 start_point로 복귀하지 않고 마지막 장소에서 끝
  "members": [                          // 1~8명
    {"name": "민지", "wants": [
      {"text": "전시 하나는 꼭", "kind": "visit", "what": "전시", "strength": "강", "must": true},
      {"text": "골목 구경도", "kind": "visit", "what": "골목", "count": 2}
    ]},
    {"name": "지훈", "wants": [
      {"text": "많이 걷기 싫어", "kind": "walk_less", "strength": "강"},
      {"text": "3시 전엔 밥", "kind": "eat_by", "time": "15:00"}
    ]},
    {"name": "서연", "wants": [
      {"text": "카페에서 쉬고 싶어", "kind": "rest", "what": "카페"},
      {"text": "2만원 안으로", "kind": "budget", "amount": 20000},
      {"text": "재밌게 놀자", "kind": "other"}
    ]}
  ],
  "candidates": null                    // 선택. vooy가 다른 연동으로 찾은 장소 목록(§3.5)
}
```

`kind`(공개 기본값표, §4):

| kind | 뜻 | 추가 필드 | 하드/소프트 |
|---|---|---|---|
| `visit` | 이런 곳에 가고 싶다 | `what`(자유 한국어, 서버가 카테고리로 정규화), `count`(기본 1) | `must: true`면 하드(최소 count곳), 아니면 체크리스트 |
| `avoid` | 이런 곳·특정 장소는 싫다 | `what` 또는 `place_name` | 하드(후보에서 제외) |
| `walk_less` | 덜 걷고 싶다 | `max_km`(선택) | 체크리스트(강도별 기준값), `must`면 하드 상한 |
| `rest` | 쉬고 싶다(카페 등에서 머물기) | `what`(기본 카페), `minutes`(기본 50) | 체크리스트 |
| `slow` | 느긋하게, 적게 돌기 | `max_stops`(선택) | 체크리스트 |
| `eat_by` | 몇 시 전에 밥 | `time` | 하드(식당 1곳이 그 시각 전에 시작) |
| `leave_by` | 몇 시엔 가야 함 | `time` | 하드(그 사람 기준 → 전체 종료 시각을 당김) |
| `budget` | 1인 지출 상한 | `amount`(원) | 하드(Σ 1인 가격 ≤ 최소 예산) |
| `other` | 위에 안 맞는 말 | — | 계산 제외, 결과에 "확인할 수 없음"으로 그대로 돌려줌 |

- `strength`: `강`/`보통`/`약`(영문 strong/normal/weak도 받음). 숫자 가중치는 서버 표에서
- 모르는 `kind`·`what`은 오류가 아니라 `other`로 강등하고 `unmapped[]`에 이유와 함께 돌려준다

출력 `structuredContent`(위젯·보드 공용 계약, 버전 필드 포함):

```jsonc
{
  "v": 1,
  "status": "ok",                 // ok | infeasible | partial(일부 말 미반영)
  "problem_id": "p_9f3k…",        // 22자 이상 무작위
  "board_url": "https://<host>/b/<board_token>",   // 공개 주소를 알 때만
  "area": "성수", "window": {"start": "13:00", "end": "18:00"},
  "members": [{"name": "민지", "color": "pink"}, …],
  "search_space": 774144,         // 후보 조합 수(근사, 표시용)
  "solve_ms": 1340,
  "plans": [{
    "plan_id": "balanced",        // balanced | favor:<name>
    "label": "균형",
    "stops": [{"place_id": "…", "name": "…", "category": "cafe", "arrive": "13:02", "leave": "13:52",
               "walk_m": 208, "price": 0, "source": "sample|mrt|vooy", "flags": ["영업시간 미확인"]}],
    "per_person": [{"name": "민지", "pct": 79, "items": [
        {"text": "전시 하나는 꼭", "fill": 1.0, "weight": 1.0, "status": "met|partial|missed|yielded|unmapped"}]}],
    "min_pct": 76, "walk_km": 2.4, "cost_per_person": 15000, "end": "16:35"
  }],
  "default_plan_id": "balanced",
  "diff": null,                   // adjust 뒤: {"added":[], "dropped":[], "pct_delta":{"민지":-3}}
  "concessions": [],              // infeasible일 때 §3.3 형식
  "unmapped": [{"name": "서연", "text": "재밌게 놀자", "reason": "장소 데이터로 확인할 수 없는 말"}],
  "data_labels": {"solver": "실제 계산", "places": "샘플(성수)", "mrt": "실호출|실패|미사용", "walk": "직선거리×1.3 추정"}
}
```

`content` 텍스트 규칙: 12줄 이내, 안마다 "라벨 · 사람별 % · 장소 → 장소(시각)", 마지막 줄에 미반영 말과 데이터 라벨, 보드 링크. 장소·사람 이름은 따옴표로 감싸고 명령문처럼 보이는 문자열은 넣지 않는다(§6).

### 3.2 `adjust_plan` (model + app)

입력 `{problem_id, action}`. `action`은 하나:
- `{"type": "yield", "name": "서연", "text": "2만원 안으로"}` — 그 말을 양보(가중치 0, 하드면 해제). `text`는 부분 일치 허용
- `{"type": "weights", "weights": {"민지": 0.5, "지훈": 1.0, "서연": 1.0}}` — 저울(0~1)
- `{"type": "add", "place_name": "…"}` / `{"type": "remove", "place_name": "…"}`
- `{"type": "undo"}` — 직전 상태로

출력: `propose_plans`와 같은 모양 + `diff`. 상태는 problem 단위로 버전(`rev`)을 올린다. 위젯이 오래된 `rev`로 부르면 최신 상태 기준으로 처리하고 `rev`를 돌려준다.

### 3.3 `explain_infeasible` (model + app)

`propose_plans`가 불가능하면 **자동으로 같이 계산해서** `status: "infeasible"`와 `concessions`를 넣는다(vooy가 두 번째 도구를 안 불러도 되게). 이 도구는 vooy가 "왜 안 돼?"에 다시 물을 때용.

```jsonc
"concessions": [{"id": "c1", "who": "지훈", "give_up": ["걷기 상한 1.5km → 2.3km"], "then_min_pct": 71,
                 "apply": {"type": "yield", "name": "지훈", "text": "많이 걷기 싫어"}}]
```

한 개짜리 양보부터, 없으면 두 개 조합. 최대 4개. 누구의 무엇인지 사람 이름을 꼭 붙인다.

### 3.4 `find_candidates` (model)

입력 `{area, kinds?: ["체험"], date?}` → `{candidates[], source_status}`. 성수 샘플 + 마이리얼트립 공개 MCP `searchTnas`(query는 `"서울 " + area + " " + 종류`, 결과를 주소·제목에 area가 들어간 것만 남김) 실호출. 실패해도 샘플로 답하고 `mrt: "실패"`.

### 3.5 vooy가 넘기는 후보 형식

```jsonc
{"name": "…", "lat": 37.54, "lng": 127.05, "category": "카페",   // 자유 한국어 → 정규화
 "open": "11:00", "close": "21:00", "stay_min": 50, "price": 8000, "rating": 4.5, "reviews": 120}
```

좌표 없는 후보는 버리고 `unmapped`에 "좌표 없음"으로 알린다. 영업시간이 없으면 하루 종일 연다고 보고 `flags: ["영업시간 미확인"]`.

### 3.6 서버 쪽 말 정리 폴백 (04에서 추가, 선택)

기본은 vooy LLM이 `kind`를 채운다. vooy가 `text`만 넘기거나 `kind`가 비면:
1. 규칙 기반(동의어표·시간·금액 패턴)으로 먼저 채운다
2. 그래도 남으면 OpenAI `OPENAI_MODEL`(기본 `gpt-6.1-sol`, JSON 모드, 타임아웃 12초)로 `kind`·`what`·`strength`만 고르게 한다. 숫자 기준값은 여전히 §4 표에서. 참고 구현: `../tripfit/server/parsing.py`(복사해서 쓰고 원본은 수정하지 않는다)
3. 키가 없거나 실패하면 `other`로 강등. 도구 전체 시간 상한 안에서만 시도하고, 결과 `data_labels.parse`에 "vooy" / "규칙" / "OpenAI" / "미반영" 표기

## 4. 공개 기본값표 (서버 고정, README에 그대로 공개)

| 항목 | 값 |
|---|---|
| 강도 → 가중치 | 강 1.0 / 보통 0.7 / 약 0.4 |
| `walk_less` 기준(체크리스트 1 → 0) | 강 1.5km → 3.5km, 보통 2.5km → 4.5km, 약 3.5km → 6km. `max_km` 있으면 그 값 → +2km |
| `slow` | 3곳 이하 1 → 7곳 0 |
| `rest` | 50분 머물면 1 |
| 카테고리 동의어 | 전시: 전시·미술관·갤러리·박물관·팝업 / 식당: 밥·점심·저녁·식당·맛집·식사 / 카페: 카페·커피·디저트·베이커리 / 소품샵: 소품샵·편집샵·쇼핑·구경 / 골목: 골목·거리·동네 구경 / 공원: 공원·산책·숲 / 체험: 체험·공방·클래스·원데이 |
| 도보 추정 | 직선거리 × 1.3, 분속 70m |
| 기본 체류 | 전시 60 / 식당 60 / 카페 50 / 소품샵 30 / 골목 30 / 공원 40 / 체험 120분 |
| 3안 | 균형(max-min) + 최소 만족도가 가장 낮은 사람 우선 + 말이 가장 많은 사람 우선(같은 안이면 합치고 2안만) |

## 5. 견고성 (실사용 가정)

| 상황 | 동작 |
|---|---|
| 이름 중복·빈 이름·이모지·긴 이름 | 앞뒤 공백 제거, 20자 자름, 빈 이름은 "친구1", 중복은 "민지(2)" |
| 1명만 | 계산은 하되 "한 사람 코스"라고 말함 |
| 9명 이상, 말 9개 이상, 글자 200자 초과, 후보 40곳 초과 | 잘라서 처리하고 `unmapped`/경고에 무엇을 잘랐는지 |
| 모르는 동네 + 후보 없음 | 마이리얼트립 실호출만으로 시도 → 그래도 없으면 `status: "need_candidates"`와 "vooy에서 장소를 찾아 candidates로 넘겨 달라"는 안내 |
| 창 시간 이상(끝 < 시작, 12시간 초과) | 명확한 오류: 필드 경로 + 고칠 방법 |
| 모든 말이 `other` | 장소 점수(Q)만으로 코스 + "조건으로 바꿀 수 있는 말이 없었다" |
| 솔버 시간 초과(3초) | 그때까지의 가장 좋은 해, 없으면 탐욕 휴리스틱 코스 + `flags: ["근사해"]` |
| 동시 호출 | CBC는 프로세스 전역 stdout을 바꾸므로 **솔버는 전역 락으로 직렬화**. 대기 8초 넘으면 `busy` 오류(재시도 안내). 전체 도구 시간 10초 상한 |
| 서버 재시작으로 problem 없음 | `problem_not_found` + "다시 propose_plans를 불러 달라" |
| 예외 | 스택트레이스 금지. `{code, message, field?, hint}` 한국어 |

모든 오류도 `content` 텍스트로 사람이 읽을 수 있게 준다(`isError: true`).

## 6. 보안

| 위협 | 대응 |
|---|---|
| 공개 ngrok 주소 남용 | 선택적 Bearer(`HAPUI_TOKEN` 있으면 필수), IP·토큰별 요청 제한(분당 60, 솔버 호출 분당 20), 요청 본문 64KB 상한 |
| DNS 리바인딩 | SDK `TransportSecuritySettings(allowed_hosts=…)`: `localhost`, `127.0.0.1`, `HAPUI_PUBLIC_HOST` 환경 변수 |
| 입력 주입(XSS) | 사람 이름·말·장소명은 모두 비신뢰. 위젯·보드는 `textContent`만 쓰고 `innerHTML`에 사용자 문자열 금지. 제어문자·양방향 제어문자 제거 |
| 프롬프트 주입 | MRT·vooy가 준 장소명과 사용자 말은 데이터. `content` 텍스트에 따옴표로만 넣고, "무시하라" 같은 지시문이 있어도 그대로 인용만. 서버는 받은 텍스트로 어떤 동작도 하지 않음 |
| SSRF | 외부 호출은 고정 주소 1곳(`https://mcp-servers.myrealtrip.com/mcp`)뿐. 사용자 URL을 열지 않음. 5초 타임아웃, 응답 1MB 상한 |
| 보드 링크 추측 | `board_token`은 `secrets.token_urlsafe(24)`, problem_id와 별개. 6시간 TTL, LRU 500개. 만료되면 "만료됨" 화면 |
| 보드 페이지 | CSP `default-src 'none'; script-src 'nonce-…'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` |
| 위젯 | 외부 리소스 0개(폰트·스크립트·이미지 전부 인라인). 그래서 `_meta.ui.csp` 기본값(connect-src none)으로 동작. 서버 호출은 호스트 브리지 `tools/call`로만 |
| 비밀값·개인정보 | 키는 상위 폴더 `.env`에서만. 로그에 사람 말·이름을 쓰지 않음(길이·개수만). 메모리에만 저장, 디스크 저장 없음 |

## 7. 화면 (위젯 = 보드, 한 HTML 파일)

- 파일 하나 `ui/board.html`. 두 모드: **App 모드**(MCP Apps 호스트 iframe. `ui/initialize` 핸드셰이크, `ui/notifications/tool-result`로 `structuredContent` 수신, 버튼은 `tools/call adjust_plan`) / **Web 모드**(`/b/<token>`. `GET /api/board/<token>`, `POST /api/board/<token>/adjust`)
- 레이아웃: 모바일 먼저(폭 320~480px에서 완성, 넓으면 2열). 위에서 아래로
  1. **아일랜드**: "3안 · 1.3초 · 가능한 조합 77만" / 계산 중엔 스피너, 끝나면 "카페 1곳 들어오고 골목 1곳 빠져요"
  2. **안 탭**: 균형 / 지훈 우선 / 민지 우선(알약 3개, 선택한 안은 라임)
  3. **사람 막대**: 사람마다 색 블록(분홍·하늘·피치·버터·민트·라일락 순), 큰 숫자 %, 체크리스트 항목(충족 ✓ / 부분 ◐ / 못 함 ✕ / 양보 ⤺ / 확인 불가 ?)과 항목별 "양보" 알약 버튼
  4. **저울**: 사람별 슬라이더(0~1). 손을 뗄 때만 재계산(디바운스 400ms)
  5. **타임라인**: 장소 카드(시각, 체류, 다음까지 도보 m, 출처 배지 샘플/실호출)
  6. **양보 카드**(불가능할 때): 카드마다 "누가 무엇을" + "그러면 최소 N%" + 적용 버튼
  7. **바닥 라벨**: 데이터 출처(실제 계산 / 샘플 / 실호출) — 과장 금지
- 스타일: `tripfit/SCREENS.md` §3 벤토 모자이크(네이비 틈 4px, 단색 파스텔 블록, 라임 = 합의). 폰트는 시스템 스택(`-apple-system, "Apple SD Gothic Neo", "Pretendard", system-ui, sans-serif`)
- 호스트 테마: `hostContext.theme`이 dark면 바탕만 더 어둡게, 블록은 채도 유지. `safeAreaInsets` 반영. 높이는 내용에 맞추고 `ui/notifications/size-changed` 보고
- 접근성: 버튼 44px 이상, 대비 4.5:1, 슬라이더 키보드 조작, `aria-live`로 아일랜드 문구 읽기

### 7.1 모션

| 대상 | 동작 |
|---|---|
| 첫 등장 | 블록이 위에서부터 40ms 간격으로 아래에서 튀어 오름(스프링, CSS `linear()` 이징) |
| % 숫자 | 자리별 롤링(이전 → 새 값) |
| 막대 | 폭 변화는 `transform: scaleX`로, 스프링 오버슈트 약간 |
| 타임라인 재배치 | FLIP: 남는 카드는 새 자리로 미끄러지고, 새 카드는 아래에서 튀어 오르고, 빠지는 카드는 살짝 기울며 왼쪽으로 사라짐 |
| 아일랜드 | 계산 중 알약 → 결과 문장 길이만큼 펼쳐짐 |
| 양보 버튼 | 누르면 항목이 회색으로 접히며 ⤺ 표시, 다른 사람 막대가 오르는 게 동시에 보임 |
| 원칙 | `transform`/`opacity`만 애니메이션, 400ms 이내, `prefers-reduced-motion`이면 즉시. 재계산 중 화면은 이전 결과를 유지(빈 화면 금지) |

## 8. 구조

```
vooy-mcp/
  PRD.md  IDEAS.md  README.md  RECIPE.md
  pyproject.toml / requirements.txt
  hapui/
    __init__.py
    engine/tripfit_solver.py      # tripfit/solver에서 복사(출처 주석). 수학 변경은 예산·eat_by 제약 추가만
    engine/places_seongsu.py      # 성수 샘플(식당 4곳 추가, 전부 sample 라벨)
    schema.py                     # pydantic 입력·출력 모델, 정규화, 한도
    mapping.py                    # wants → Pref/Request, 동의어표, 공개 기본값표
    planner.py                    # 3안·adjust·diagnose·근사해 폴백, 전역 솔버 락
    store.py                      # problem/board 토큰 저장(TTL·LRU·rev·undo)
    mrt.py                        # 마이리얼트립 공개 MCP 클라이언트(고정 URL)
    text.py                       # content 텍스트 렌더
    server.py                     # MCPServer + Apps, Streamable HTTP(stateless, JSON), /b, /api/board, /healthz, 보안 미들웨어
  ui/board.html
  ui/sample_state.json            # §3.1 계약 예시(화면 개발용)
  tests/
  scripts/smoke_mcp.py            # 원격 URL에 initialize → tools/list → tools/call
  scripts/run_public.sh           # 서버 + ngrok
```

실행: `.venv/bin/python -m hapui.server --port 8765`(HTTP, 기본) / `--stdio`(로컬 테스트). vooy 등록 주소 `https://<ngrok>/mcp`.

## 9. 완료 기준

1. `scripts/smoke_mcp.py http://127.0.0.1:8765/mcp`가 §2 시나리오로 3안 텍스트를 받고, 양보·불가능·이상 입력 6종을 통과
2. `pytest` 통과(정규화, 한도, 오류 모양, 동시 호출 10개, 토큰 만료, XSS 문자열이 HTML에 그대로 안 박힘)
3. 보드 `/b/<token>`이 폰 폭 390px에서 깨지지 않고 양보 버튼으로 막대가 바뀜(스크린샷)
4. ngrok 주소로 vooy 연결 → 메신저에서 `propose_plans` 1회 끝까지(사람이 확인)
5. README에 실호출/샘플 구분과 공개 기본값표

## 9.1 심사 방식에 맞춘 조정 (총괄 세션 확정, 12:10)

- Vooy 트랙은 **원격 MCP 서버만 있으면 된다**(레시피·보드는 선택). 무대 시연은 메인 트랙만
- 스폰서가 빌드 보드의 **GitHub·링크만 보고 고른다** → (a) 심사 시점에 https MCP 주소가 살아 있어야 하고 (b) README만 읽고 vooy에 붙여 체험할 수 있어야 한다
- README 필수 항목: 서버 URL, vooy 연결법(서비스 연결 화면에 URL 붙여넣기), 도구 4개 입출력 예시, 예시 대화와 결과 스크린샷, 실호출/샘플 구분, 공개 기본값표, 로컬 실행법

## 9.2 배포 후보 (외부 공개라 사용자 승인 필요, 계정은 사용자가 직접 로그인)

| 후보 | 장점 | 단점·위험 | 판단 |
|---|---|---|---|
| **Hugging Face Spaces (Docker, 무료 CPU)** | 카드 등록 없이 무료, 고정 https 주소, Linux x86(CBC 동작) | 오래 접속이 없으면 잠듦(무료 CPU는 비활동 48시간 뒤 일시정지라는 문서가 있으나 최신 정책 미확인). 깨어날 때 수십 초 → vooy 첫 호출이 실패할 수 있음. 공개 Space는 코드가 보임(어차피 GitHub 공개) | **추천**. 외부 핑(무료 업타임 모니터 5분 간격)으로 잠들지 않게 |
| Render 무료 웹 서비스 | GitHub 연결 자동 배포 | 비활동 시 잠들고 콜드스타트가 김(정확한 분 수 미확인) | 대안 |
| Fly.io / Railway | 상시 구동 | 신규 계정은 체험 크레딧·카드 등록 필요 | 비용 감수 시 |
| 노트북 + ngrok | 지금 바로 | 노트북이 꺼지면 주소가 죽고, 무료 주소는 재실행마다 바뀜 | 개발·현장 확인용 |

### AWS (사용자 제안, 2026-11-07 읽기 전용 점검)

- 배포 계정: 팀원의 AWS 계정(조직 소속, 관리자 역할), 리전 ap-northeast-2. 계정 식별자는 공개 저장소에 적지 않는다. 기존 리소스와 이름이 겹치지 않게 `hapui` 이름을 쓴다
- 로컬: Docker 27.5(arm64, buildx로 linux/amd64 빌드 가능), `lightsailctl` 없음(이미지 푸시에 필요 → `brew install aws/tap/lightsailctl`)

| 경로 | 장점 | 단점 | 판단 |
|---|---|---|---|
| **Lightsail Container Service (서울)** | 고정 https 주소(`*.cs.amazonlightsail.com`), 노드 1개라 메모리 상태(problem·보드 토큰)가 한 곳에 유지, 정액(micro 1GB 월 $10, nano 0.5GB 월 $7), 헬스체크 내장 | lightsailctl 설치 필요, 배포 1회 5~10분 | **추천**(micro, scale 1) |
| App Runner (도쿄) | ECR 연동, 자동 https | 서울 미지원(엔드포인트 없음 확인), 인스턴스가 늘면 메모리 상태가 갈림 | 대안 |
| Lambda + Function URL | 거의 무료 | 인스턴스마다 메모리가 달라 `adjust_plan`의 problem_id를 못 찾음, 콜드스타트 | 비추천 |
| EC2 + Caddy | 자유도 | TLS용 도메인·운영 부담 | 비추천 |

절차(승인 뒤): Dockerfile(linux/amd64) 로컬 빌드·스모크 → `create-container-service --service-name hapui --power micro --scale 1` → `push-container-image` → 배포(포트 8765, 헬스체크 `/healthz`, 환경 변수 `HAPUI_PUBLIC_HOST`·`HAPUI_PUBLIC_URL`) → https 스모크 → vooy 등록. 심사 끝나면 `delete-container-service`. `OPENAI_API_KEY`는 넣지 않거나(§3.6 OpenAI 단계 생략) 넣으면 Lightsail 환경 변수라 계정 관리자에게 보인다는 점을 감수.

배포 공통: `Dockerfile`(python:3.11-slim, `PORT` 환경 변수, `HAPUI_PUBLIC_HOST`/`HAPUI_PUBLIC_URL` 설정), `OPENAI_API_KEY`는 호스팅 비밀값으로(선택, 없으면 §3.6 OpenAI 단계 생략), 요청 제한으로 크레딧 남용 방지. 확인 필요: CBC 바이너리가 컨테이너(Linux x86_64)에서 `mip`과 함께 동작하는지 — Docker로 로컬 빌드해 스모크.

## 10. 위임 순서

| # | 브리프 | 모델 | 병렬 |
|---|---|---|---|
| 01 | 서버 전체(§3~§6, §8 중 ui 제외) | gpt-6-astra high | 03과 동시 |
| 03 | `ui/board.html` + `ui/sample_state.json`(§7) | gpt-6.1-sol high(화면 비중이 커서 high) | 01과 동시 |
| 04 | 통합 수정(리뷰 결과), RECIPE.md, README, run_public.sh | gpt-6.1-sol medium | 01·03 뒤 |
