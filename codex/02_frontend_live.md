# 02 — 프론트를 실제 백엔드에 연결 + "이 말은 양보할게"

너는 `tripfit/` 폴더에서 일한다. 01 작업으로 `server/app.py`(FastAPI)가 생겼고 `.venv/bin/uvicorn server.app:app --port 8000`로 띄우면 `/`에서 `web/index.html`을 서빙한다. 지금 프론트는 `web/demo_data.js`(`window.DEMO`)만 재생한다. 이걸 "실제로 돌아가는" 화면으로 바꾼다. 먼저 `README_RUN.md`, `server/app.py`, `web/index.html`의 구조(s0~s5 단계 함수, `paint`, `renderChecklist`, `log`, `island`)를 읽어라.

## 할 일

1. **라이브 모드 감지** (`web/index.html`)
   - 페이지가 http(s)로 열렸고 `GET /api/demo`가 성공하면 그 응답으로 `window.DEMO`를 대체하고 `LIVE = true`. 실패하거나 `file://`이면 기존 `demo_data.js` 재생(`LIVE = false`).
   - 엔진 패널 상단 라벨에 상태를 보여준다: 라이브면 "LIVE · 실시간 계산", 재생이면 "재생 · demo_data.js". 엔진 로그 첫 줄에도 남긴다.
   - 앱이 첫 화면을 그리기 전에 감지를 끝낸다(최대 3초 대기 후 재생으로 진행).
2. **1단계 파싱 실호출** — 라이브면 1단계 진입 시 `POST /api/parse`에 두 사람 문장(`D.people[].text`)을 보낸다. 화면의 칩 애니메이션은 지금처럼 `marks`로 하되, 응답이 오면 엔진 로그에 `LLM <model> · <ms>ms`(fallback이면 "고정 JSON")와 추출된 항목 수를 찍는다. 응답을 기다리느라 애니메이션을 멈추지 마라.
3. **"이 말은 양보할게" 토글** (2단계 체크리스트 블록)
   - 각 체크리스트 행을 누르면 그 항목을 양보(muted) 상태로 토글한다. 양보한 행은 라벨에 취소선 + "양보" 작은 알약, 막대는 흐리게.
   - 라이브면 `POST /api/plan {muted:[{person,label}...], tag_min:{}}`을 부르고 받은 `series`·`defaultIdx`로 저울을 다시 만든다(점 개수가 바뀔 수 있으니 트랙의 점을 다시 그리고 thumb를 `defaultIdx`로). 계산 중엔 아일랜드 스피너, 끝나면 아일랜드에 "<사람>의 '<항목>' 양보 → 지민 A · 서연 B"와 `solveMs`.
   - 재생 모드면 토글을 막고 아일랜드에 "서버 연결 시 동작해요"를 띄운다.
   - `H`(숨은 한 곳)가 켜져 있으면 토글 전에 끈다.
4. **넣어보기·재계산 실호출** — 라이브면 3단계 [넣고 다시 계산]은 `POST /api/what-if {pick}`, 5단계 [다시 짜기]는 `POST /api/replan {now_min, exclude:[붐비는 곳], keep:{공방 id: 시작분}}` 결과를 쓴다. 실패하면 기존 demo 데이터로 폴백.
5. **겹치는 일정 정리** (`solver/demo_builder.py`) — 파레토 목록에서 두 사람 만족도(소수 1자리)가 같은 일정은 하나만 남긴다(걷는 거리가 짧은 쪽). `/api/plan`과 `/api/demo` 모두에 적용. `server/test_api.py`에 "서연 '덜 걷기' muted 시 series에 같은 만족도 쌍이 없다" 테스트를 추가.
6. **README.md** (저장소 첫 화면) — 한 문단 소개, 핵심 아이디어 3줄(만족도 = 한 말의 체크리스트 / 장소 점수 / LLM은 숫자를 만들지 않는다), 실행 방법(`README_RUN.md` 요약), 무엇이 실호출이고 무엇이 샘플인지 표, 문서 링크(PRD.md, SCREENS.md), 솔버 출처 한 줄("행사 전 공개한 개인 최적화 알고리즘을 확장"). 한국어.

## 규칙

- 디자인 문법(벤토 블록, 색, 폰트, 스프링 애니메이션)은 그대로 유지. 새 요소도 기존 클래스(`.pill`, `.b`, `.ci` 등)를 재사용.
- 키·비밀값을 프론트 코드나 README에 쓰지 마라. 프론트는 서버 API만 부른다.
- `solver/tripfit_solver.py`는 수정하지 마라.
- 완료 기준: `.venv/bin/python -m pytest server -q` 통과, `(cd solver && ../.venv/bin/python test_solver.py)` 통과, `web/index.html`의 `<script>` 본문이 `node --check`로 문법 오류 없음(스크립트를 임시 파일로 뽑아서 검사), `file://`로 열었을 때 기존 재생 동작이 깨지지 않음(코드상 분기 확인).

## 마지막 메시지 형식

바뀐 파일, 라이브/재생 분기 설명, 토글 동작 설명, 테스트 결과, 확인하지 못한 것(브라우저 실제 렌더 등).
