# 01 — TripFit 백엔드: 솔버를 실제로 돌리는 FastAPI

너는 지금 `tripfit/` 폴더에서 일한다. 해커톤 메인 트랙 기준이 "하루 안에 실제로 돌아가는 MVP"라서, 지금 미리 계산한 `web/demo_data.js`를 재생하는 프로토타입을 실제 솔버 호출로 돌아가게 만드는 백엔드가 필요하다. 먼저 `PRD.md`(특히 §5, §6.2, §6.3, §6.6, §10)와 `solver/` 코드를 읽어라.

## 만들 것

1. **`solver/demo_builder.py`** — `solver/export_demo.py`의 계산 부분을 함수로 분리한다.
   - `build_demo(request=REQUEST, places=PLACES, hidden=HIDDEN, messages=MESSAGES, muted=()) -> dict`가 지금 `window.DEMO`와 **같은 모양의 dict**를 돌려준다(키 이름·중첩 구조 동일).
   - `muted`는 `[(person, label), ...]`. 해당 체크리스트 항목의 가중치를 0으로 바꿔 푼다("이 말은 양보할게"). 화면에 항목은 남아야 하므로 checklist 출력에는 그대로 나오되 `weight: 0`, `muted: true`로 표시한다.
   - `export_demo.py`는 이 함수를 불러 파일을 쓰도록 바꾼다(결과는 ms 값을 빼면 지금과 같아야 한다).
2. **`server/app.py`** — FastAPI.
   - `GET /api/health` → `{ok, solver: "CBC", llm: {"axk2": bool, "openai": bool}}` (키 존재 여부만, 값은 절대 노출 금지)
   - `GET /api/demo` → `build_demo()` 결과(메모리 캐시, `?fresh=1`이면 다시 계산). 응답에 `"live": true`와 계산 시각을 추가.
   - `POST /api/plan` `{muted: [{person, label}], tag_min: {}}` → `{series, defaultIdx, diffs, solveMs, live: true}`. 불가능하면 `solve_or_explain` 결과로 `{infeasible: true, relaxations: [{label, changes: [...]}]}` (빈 화면 금지).
   - `POST /api/what-if` `{pick: "mrt_leather_1600" | "mrt_leather_1400"}` → `{plan, diff}` (기준은 균형안)
   - `POST /api/replan` `{now_min, exclude: [], keep: {place_id: start_min}}` → `{plan}`
   - `POST /api/parse` `{messages: [{name, text}]}` → `{constraints, model, ms, fallback}`.
     - 순서: SKT A.X K2(`OBA_API_KEY`, `OBA_BASE_URL`, `OBA_MODEL`, OpenAI 호환, `response_format={"type":"json_object"}`) → OpenAI(`OPENAI_API_KEY`, 모델은 `OPENAI_MODEL` 환경 변수, 없으면 이 단계 건너뜀) → 데모 문장용 고정 JSON(`export_demo.MESSAGES`와 `sample_seongsu.PREFS`에서 만든 것). 각 단계 5초 타임아웃.
     - LLM은 항목 `label`, `kind`(visit/dwell/walk/stops), `intensity`(strong/normal/weak), `quote`, 말에 수량이 있을 때만 `full`을 고른다. 숫자 기준값과 `match`는 서버의 고정 기본값표(`PRD.md` §6.3)로 채운다. 스키마 검증 실패 시 1회 재시도 후 다음 단계로.
   - `/`에 `web/` 정적 파일을 서빙해서 `http://localhost:8000/`이 프로토타입을 연다.
   - 솔버 호출은 전역 `threading.Lock`으로 직렬화한다(`_quiet_native_stdout`이 fd를 바꾸므로 동시 실행 금지). 시작할 때 1회 워밍업.
   - `.env`는 상위 폴더(`tripfit/../.env`)에서 `python-dotenv`로 읽는다. 키 값을 로그·응답·파일에 쓰지 않는다.
3. **`server/test_api.py`** — FastAPI `TestClient`로: health, `/api/demo`의 최상위 키가 `web/demo_data.js`의 키와 같음, `/api/plan`에 서연의 "덜 걷기"를 muted로 주면 series가 바뀌고 해당 항목이 `muted: true`, `/api/parse`가 키 없이도 고정 JSON으로 동작(`fallback: true`), `/api/what-if`와 `/api/replan`이 plan을 돌려줌.
4. **`README_RUN.md`** — 실행 방법: `cd tripfit && .venv/bin/uvicorn server.app:app --port 8000`, 테스트 명령, 환경 변수 목록, 무엇이 실호출이고 무엇이 샘플인지.

## 규칙

- Python은 `tripfit/.venv`를 쓴다(이미 fastapi, uvicorn, openai, python-dotenv, pytest, mip 설치됨). 새 패키지가 꼭 필요하면 `requirements.txt`에 추가하고 이유를 남겨라.
- `solver/tripfit_solver.py`의 수학(목적함수·제약)은 바꾸지 마라. 필요한 건 래퍼로.
- `web/index.html`은 이번에 수정하지 마라(프론트 연결은 다음 작업).
- 끝나면 `cd solver && ../.venv/bin/python test_solver.py`와 `../.venv/bin/python -m pytest server -q`(tripfit 폴더 기준 경로로 맞춰서)가 모두 통과해야 한다. `export_demo.py`를 다시 돌려 `web/demo_data.js`가 같은 모양으로 재생성되는지 확인하라.

## 마지막 메시지 형식

바뀐/새 파일 목록, 엔드포인트별 요청·응답 예시 1줄씩, 실행·테스트 명령과 결과, 남은 목업·샘플, 확인하지 못한 것.
