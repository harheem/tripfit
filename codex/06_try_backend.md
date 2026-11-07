# 06 — "직접 해보기" 백엔드: 아무 두 문장 → 전체 데모 데이터

너는 `tripfit/` 폴더에서 일한다. 지금 `/api/parse`는 두 사람 문장을 Constraint JSON(`people[].prefs`, `people[].hard`)으로 바꾸지만, 일정 API(`/api/demo`, `/api/plan`, `/api/what-if`, `/api/replan`)는 언제나 `solver/sample_seongsu.py`의 고정 PREFS·REQUEST로 계산한다. README 한계에 "임의 문장 → 일정 세션 미지원"이라고 적혀 있다. 이걸 없앤다. 먼저 `README.md`, `server/app.py`, `server/parsing.py`, `solver/demo_builder.py`, `solver/export_demo.py`, `solver/sample_seongsu.py`, `server/test_api.py`를 읽어라.

## 만들 것

1. **`POST /api/try {people:[{name:"지민",text:"..."},{name:"서연",text:"..."}]}`** (이름은 지민·서연 고정, 문장은 각 1~200자)
   - `/api/parse`와 같은 경로로 파싱(OpenAI → 실패 시 아래 규칙 파서). 결과 prefs를 `solver.Pref`로, hard를 `Request`(category_min, max_walk)로 바꾼다. 수치(weight·match·full·zero)는 지금처럼 서버 규칙(`parsing.py`의 기본값 표)만 쓴다.
   - 그 Request로 `build_demo(request, places, hidden, messages)`를 돌려 **`/api/demo`와 같은 모양**의 JSON을 돌려준다. 화면이 `window.DEMO`만 바꾸면 1~5단계가 그대로 돌게 하는 것이 목표다. `people[].text`는 입력 문장, `people[].marks`는 파싱된 quote 구절 → 라벨(입력 문장 안의 연속 구절만; 없으면 빈 배열).
   - 응답에 `sessionId`(uuid4), `source: {provider: "openai"|"rules", model, parseMs, solveMs}`, `unmatched: {지민:[...], 서연:[...]}`(이해하지 못한 말: 6개 조건 어휘에 안 맞는 구절. LLM이 돌려주면 그걸, 규칙 파서면 빈 배열)를 넣는다.
   - 어느 한 사람의 prefs가 0개면 400이 아니라 200으로 `{needsMore: true, person, hint}`를 돌려준다(화면이 "서연의 말에서 조건을 못 찾았어요. 예: '카페에서 쉬고 싶어'"를 띄움).
   - 불가능하면 `solve_or_explain`/diagnose 결과를 담아 `{infeasible:true, explanation}`(기존 조건 충돌 설명 모양 재사용).
2. **세션** — 메모리 LRU(최대 100개, 30분)에 `sessionId → (request, places, messages)`. `/api/plan`, `/api/what-if`, `/api/replan`이 선택 인자 `sessionId`를 받으면 그 request로 계산한다. 없거나 만료면 기존 샘플(하위 호환) — 만료면 응답에 `sessionExpired: true`.
3. **규칙 파서(키 없이도 동작)** — `server/parsing.py`에 `rule_parse(people)`: 키워드로 6개 조건(전시, 골목, 소품샵, 카페에서 쉬기, 덜 걷기, 느긋하게)을 찾는다. 강도는 "꼭/무조건/반드시/절대" → strong, "좀/조금/웬만하면" → weak, 그 외 normal. 부정("전시는 별로", "카페 말고")은 제외. quote는 입력 안의 실제 구절. OpenAI 키가 없거나 실패·타임아웃이면 이걸 쓴다(기존 "고정 JSON" 폴백은 `/api/parse`의 데모 전용으로만 남겨라 — 임의 문장에 샘플 결과를 돌려주면 안 된다).
4. **남용 방지(공개 배포 대비)** — `/api/try`와 `/api/parse`에 IP당 분당 6회 제한(메모리 토큰 버킷, `X-Forwarded-For` 첫 값 우선). 초과 시 429 `{error:"잠시 후 다시"}`. 환경변수 `TRY_RATE_PER_MIN`으로 조정. LLM 호출 동시성은 세마포어 2개.
5. **테스트** (`server/test_try.py`, 네트워크·키 없이): ① 규칙 파서로 "전시 꼭 보고 싶어 / 많이 못 걸어 카페에서 쉬고 싶어" → 응답이 `/api/demo`와 같은 최상위 키를 갖고 series가 1개 이상 ② 한쪽 조건 0개 → needsMore ③ 부정 표현 제외 ④ sessionId로 `/api/what-if`·`/api/replan` 호출 시 그 세션의 request를 씀(예: 전시 조건이 없는 세션에서는 category_min.exhibit가 없음) ⑤ 레이트 리밋 429 ⑥ 기존 테스트 전부 통과.

## 규칙

- `solver/tripfit_solver.py`의 수학 변경 금지. CBC 호출은 기존 `SOLVE_LOCK` 아래에서만.
- `web/` 수정 금지(화면은 다른 작업이 동시에 고친다). 
- 키·비밀값을 코드·로그·결과 파일에 쓰지 마라. 키는 상위 폴더 `.env`(이미 로드 코드 있음).
- 완료 기준: `(cd solver && ../.venv/bin/python test_solver.py)`, `.venv/bin/python -m pytest server -q` 통과. 서버를 띄워 실제로 `curl -X POST localhost:8011/api/try`를 2가지 문장 쌍(하나는 샘플과 전혀 다른 취향, 예: "골목 산책 느긋하게, 소품샵은 꼭" / "걷는 건 괜찮아 전시 위주로")으로 불러 결과 요약을 남겨라(포트 8000은 다른 서버가 쓰니 8011 사용, 끝나면 종료).

## 마지막 메시지 형식

바뀐 파일, `/api/try` 요청·응답 예시(요약), 두 문장 쌍의 결과(조건 목록, 균형안 일정·만족도, provider, 시간), 테스트 결과, 확인 못 한 것.
