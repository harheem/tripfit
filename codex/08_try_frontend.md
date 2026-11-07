# 08 — "직접 해보기" 화면: 내 두 문장으로 1~5단계 전체를 다시

너는 `tripfit/` 폴더에서 일한다. 06 작업으로 `POST /api/try {people:[{name,text}]}`가 생겼다. 응답은 `/api/demo`와 같은 모양 + `sessionId`, `source{provider,model,parseMs,solveMs}`, `unmatched`, 또는 `{needsMore,person,hint}`, `{infeasible,explanation}`, 429. `/api/plan`·`/api/what-if`·`/api/replan`은 `sessionId`를 받는다. 07 작업으로 휴대폰 모드(`body.mobile`)가 생겼다. 먼저 `codex/06_try_backend.result.md`, `codex/07_mobile.result.md`, `server/app.py`, `web/index.html`(LIVE 감지, `api()`, 0·1단계 함수, `window.DEMO` 사용처, 아일랜드, 시트 컴포넌트)을 읽어라.

## 할 일 (`web/index.html`만)

1. **0단계(대화)에 "내 말로 해보기" 버튼** — 라임 CTA 블록 옆이나 아래, 기존 `.pill`/`.b` 문법. 누르면 바텀시트: 지민(핑크)·서연(하늘) 입력칸 두 개(현재 샘플 문장이 들어 있고 지울 수 있음, 각 200자), 예시 칩 3개씩(누르면 입력칸에 채움: 예 "골목 산책 느긋하게, 소품샵은 꼭", "걷는 건 괜찮아 전시 위주로", "카페에서 오래 쉬고 싶어"), [이 말로 일정 짜기] 버튼.
2. **제출 흐름** — 아일랜드 스피너 "두 사람 말을 조건으로 바꾸는 중" → `/api/try` → 성공하면 `window.DEMO`(와 그것을 캐시한 모든 변수)를 응답으로 바꾸고, 대화 말풍선을 새 문장으로 다시 그린 뒤 1단계부터 진행한다. 1단계 칩 애니메이션은 응답의 `marks`를 쓴다. `unmatched`가 있으면 1단계 아래 회색 알약 "아직 이해 못 한 말: …"(정직하게).
   - 엔진 로그: `LLM <model> · <parseMs>ms`(rules면 "규칙 파서"), `MIP 파레토 n개 · <solveMs>ms`, `세션 <sessionId 앞 6자>`.
   - 이후 2단계 양보 토글·3단계 넣어보기·5단계 재계산 API 호출에 `sessionId`를 붙인다. 응답에 `sessionExpired`면 아일랜드 "세션이 만료돼 샘플로 계산했어요".
   - `needsMore` → 시트를 닫지 말고 그 사람 입력칸 아래 빨간 안내(`hint`). `infeasible` → 기존 조건 충돌 설명 화면(`C`)을 그 explanation으로 띄움. 429 → 아일랜드 "잠깐만요, 1분에 6번까지예요". 네트워크 실패 → "서버에 연결하지 못했어요"와 샘플 유지.
   - 3단계에 체험을 넣을 수 없는 경우(응답의 whatif.pick null 등)도 깨지지 않게: 3단계 CTA를 "체험 없이 합의하기"로 바꾸고 4단계로.
   - 숫자·문구 하드코딩(지민 79 등) 금지 — 모든 제목·캡션의 숫자는 데이터에서. `CAPS`(발표 캡션)는 샘플 전용이므로 직접 해보기 중엔 캡션 숫자 문장을 숨기거나 데이터로 채워라.
3. **재생 모드(`LIVE=false`, GitHub Pages)** — 버튼은 보이되 누르면 시트 대신 아일랜드 "직접 해보기는 서버 연결 시 동작해요 · README의 실행법 참고". 
4. **[샘플로 돌아가기]** — 직접 해보기 중일 때 0단계 상단 작은 알약. 누르면 원래 DEMO로 복귀. `R` 키도 원래 DEMO로.
5. 휴대폰 모드에서도 시트·입력칸이 키보드에 가리지 않게(`visualViewport` 대응), 데스크톱 렌더는 기존과 동일.

## 규칙

- `server/`, `solver/` 수정 금지. 디자인 문법 유지, 새 색 금지.
- 완료 기준: `node --check` 통과. 서버(`.venv/bin/uvicorn server.app:app --port 8012`, 끝나면 종료)를 띄우고 Playwright로 ① 샘플 흐름(자동재생 `A`)이 기존과 같은 숫자로 끝까지 ② 직접 해보기: 지민 "골목 산책 느긋하게, 소품샵은 꼭" / 서연 "걷는 건 괜찮아 전시 위주로" → 1~5단계 진행 스크린샷을 `codex/08_shots/`에 ③ 390×844 모바일에서 ②의 0~2단계 ④ `file://`에서 버튼 안내. 콘솔 에러 0(favicon 제외).

## 마지막 메시지 형식

바뀐 부분, 직접 해보기 결과(조건·일정·만족도), 스크린샷 경로, 콘솔 에러, 확인 못 한 것.

## 추가 A. 4단계 → SKT "같이 결제" 연결

`web/pay/`(SKT 트랙, 정적 화면, `/pay/?embed=1`로 열면 제목 영역 숨김)와 `server/pay_router.py`(`POST /api/pay/recheck`)가 붙어 있다. `web/pay/engine/tripfit.js`의 `fromTripFit({pay, plan, people, snapshot})`가 TripFit 데이터 → 결제 입력을 만들고, 페이지는 열리기 전 `window.TRIPFIT_PAY_INPUT`이 있으면 그걸 쓴다(없으면 `web/pay/data/trip.json`). `agentic-pay/README.md`와 `web/pay/` 코드를 먼저 읽어라.
- 4단계 합의 화면의 결제 블록 아래 CTA를 "예약하고 결제하기"로 하고, 누르면 전체 화면 시트 안 `<iframe src="pay/?embed=1">`로 연다(같은 출처이므로 `web/pay/`가 이미 지원하는 `window.TRIPFIT_PAY_INPUT`을 iframe 문서 스크립트 실행 전에 넣는다. 예: `fetch('pay/index.html')` 후 `srcdoc`에 `<base href="pay/">`와 입력 주입 스크립트를 앞에 붙이는 방식 등. **`web/pay/` 파일은 고치지 마라** — 다른 작업이 동시에 고친다). 입력은 **지금 화면의 합의 plan**(직접 해보기 세션이면 그 plan, 체험이 없으면 결제 항목 0개 안내).
- 시트 닫기 → 4단계로 복귀, [여행 중 화면 보기]로 5단계 진행은 그대로. 자동재생(`_run`)은 결제 시트를 열지 않는다(발표 흐름 유지). 
- 엔진 로그: `AGENTIC PAY · 위임 2건 → 재조회 → 분담 결제(모의)`.
- `web/pay/`는 수정 금지. `(cd agentic-pay && node --test test/*.test.mjs)` 25개 통과 유지.

## 추가 B. 기다리는 시간

`/api/try`는 실측 13초(OpenAI 파싱 약 8.7초 + 전체 계산 약 4.3초) 걸린다. 그동안 빈 화면이 되지 않게: 시트 위에 단계형 진행(① 말을 조건으로 바꾸는 중 · OpenAI → ② 꼭 지킬 것과 되면 좋은 것 나누기 → ③ 가능한 순서 비교 중 · CBC)과 경과 초. 30초 넘으면 취소 버튼. `series`가 1개(두 사람 모두 100%처럼 충돌이 없을 때)여도 저울이 깨지지 않게 "충돌 없음 · 둘 다 다 지켰어요" 상태로.

## 참고

09 작업으로 POI 시트·만족도 식·양보 추천·로고·`fitNumber()`가 들어갔다(`codex/09_poi_score_fit.result.md`). 이것들을 깨지 말고, 직접 해보기 데이터에서도 그대로 동작하게 하라(`/api/try` 응답에 `fills`, `facts`, `recommended`, `preview`가 실린다).
