# 08 — 미리보기를 "실제 MCP 서버와 통신하는 MCP Apps 호스트"로

너는 `vooy-mcp/` 폴더에서 일한다. 사용자 요구: **"채팅방은 데모여도 그 안의 MCP Apps는 실제 MCP 서버로 동작해야 한다."**

지금 `ui/preview.html`은 위젯 HTML을 로컬 파일에서 읽고, 결과는 `ui/fixtures/*.json`(공개 서버에서 미리 받아 둔 고정 JSON)을 쓰고, 위젯의 `tools/call`에도 fixture로 답한다. **이걸 전부 실제 서버 호출로 바꾼다.** 채팅 대본(누가 무슨 말을 하는지)만 데모로 남는다.

먼저 읽어라: `PRD.md` §3·§6, `hapui/server.py`(Guard, `board_html`, `UI_URI`, 보안 헤더), 지금 `ui/preview.html`, `ui/board.html`(App 모드 브리지), `codex/07_chat_native.md`(직전 디자인 작업, 결과는 유지).

## 0. 목적 확장 (총괄·사용자 결정, 14:50) — 마감 16:00

Vooy 심사자는 vooy 계정 없이 **링크 하나로** "메신저 단톡방에서 MCP Apps를 부르는 장면"을 봐야 한다. 그래서 미리보기를 **`/chat`** 이라는 공개 데모 페이지로 만든다(`ui/preview.html`을 `ui/chat.html`로 이름을 바꾸고 아래 요구를 반영. `/preview` 경로는 만들지 않는다).

- 휴대폰 폭 단톡방 화면: 상단 방 이름 "성수 토요일 나들이 · 3명", 말풍선(민지·지훈·서연 프로필 원형 이니셜), 아래 입력창. 일반 메신저 문법, **카카오톡 상표·노란색 브랜딩 금지(사칭 금지)**. 07의 "단톡 라이트 / DM 다크" 스킨 토글은 유지
- 봇 이름은 **TripFit**(vooy 안에서 붙은 MCP 도구라는 설정). 호출 문법 `@TripFit`
- 흐름은 **자동 재생**(시작 버튼, 말풍선이 하나씩 0.8초 간격) + **직접 입력** 둘 다:
  1. 민지 "난 전시 하나는 꼭" → 지훈 "많이 걷기 싫어. 3시 전엔 밥" → 서연 "카페에서 좀 쉬고 싶고 2만원 안으로" → 서연 "@TripFit 성수 13시부터 18시까지 코스 짜줘"
  2. 작은 **시스템 칩**(가운데 정렬 회색 알약) "TripFit · propose_plans 호출 중…" → 끝나면 "TripFit · propose_plans · 3.9초"로 바뀜(실제 측정 ms)
  3. TripFit 말풍선(결과 `content` 첫 줄) + **MCP Apps 위젯 카드**(아래 §2 방식, `resources/read`로 받은 실제 `ui://`)
  4. "다음" 버튼 또는 직접 입력 "서연은 예산 양보할게" → 시스템 칩 "adjust_plan 호출 중…" → 새 메시지에 새 카드
  5. 버튼 "조건 충돌 시나리오" → 새 대본(민지 "디뮤지엄 꼭, 공방 14시도 꼭", 지훈 "1km 넘게는 못 걸어") → 실제 `propose_plans` → infeasible 카드
- 직접 입력 규칙(LLM 없이, 정직하게): 입력 텍스트를 내 말풍선으로 추가. `@TripFit`이 들어 있고 "짜줘/정해줘/코스"면 현재 대본의 미리 정한 arguments로 `propose_plans`. 사람 이름 + "양보"가 들어 있으면 그 사람의 첫 번째 want(대본에 정의)로 `adjust_plan yield`. 그 외에는 TripFit이 "데모에서는 '@TripFit 코스 짜줘'나 '○○은 양보할게'만 알아들어요. 실제 vooy에서는 vooy가 말을 조건으로 바꿔 줍니다"라고 답함
- **정직 표기**(상단 작은 줄, 항상 보임): "vooy 연결 화면을 재현한 데모 · 계산은 공개 MCP 서버 실호출 · 장소는 성수 샘플". 접을 수 있는 "기술 정보" 패널: 호출 로그(메서드·도구·ms·HTTP 상태, 최근 10개), "말→조건 변환은 vooy LLM 몫이라 데모에선 미리 정한 arguments를 씁니다", 실제 arguments JSON 보기

## 1. 서버: `/chat` 경로 (hapui/server.py)

- `GET /chat` → `ui/chat.html` 서빙(구 preview). 같은 출처라서 미리보기 페이지가 `fetch('/mcp')`를 Origin 검사 통과로 부를 수 있다(Guard는 Origin이 Host와 같으면 허용)
- 보안 헤더: `/b`와 같은 수준. CSP는 이 페이지가 동작하는 최소한으로: `default-src 'none'; script-src 'nonce-<n>'; style-src 'unsafe-inline'; connect-src 'self'; frame-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'`. 위젯 iframe을 `srcdoc`로 띄우면 부모 CSP를 상속하므로, 위젯 HTML의 `__CSP_NONCE__`를 같은 nonce로 치환하거나 blob URL 등 동작하는 방식을 골라 **실제 브라우저에서 위젯 스크립트가 도는 방식**으로 구현하라. iframe은 `sandbox="allow-scripts"`(allow-same-origin 금지) 유지
- `chat.html`도 `__CSP_NONCE__`를 쓰는 스크립트 1개로
- 요청 제한은 Guard 그대로(별도 완화 금지). `/chat`은 데이터 없는 정적 페이지
- 테스트 추가: `/chat` 200 + CSP 헤더, 다른 Host 421

## 2. 미리보기 = 브라우저 안 MCP 클라이언트 + MCP Apps 호스트

- MCP 클라이언트(브라우저 JS, 의존성 없이): `POST /mcp`, 헤더 `Content-Type: application/json`, `Accept: application/json, text/event-stream`, JSON-RPC 2.0. 서버는 stateless + JSON 응답 모드다. `initialize`(protocolVersion `2025-06-18`, capabilities에 MCP Apps 확장 지원을 알리는 값 — `hapui/server.py`의 `client_supports_apps` 판정과 `mcp/server/apps.py`를 읽고 맞춰라) → `tools/list` → 필요한 호출. 응답이 SSE(`data:` 줄)로 와도 파싱
- 위젯 HTML: `tools/list`에서 `propose_plans`의 `_meta.ui.resourceUri`를 읽고 **`resources/read`로 서버에서 받아** 쓴다(로컬 `board.html` fetch 금지). MIME `text/html;profile=mcp-app` 확인
- 대본 흐름(대화는 데모, 호출은 실제):
  1. 민지·지훈·서연 말풍선 → 서연 "@vooy 성수 1시부터 6시까지 코스 짜줘"
  2. vooy 타이핑 표시 → **실제 `tools/call propose_plans`**(인자는 `scripts/smoke_mcp.py`의 `SCENARIO`와 같은 값) → vooy 말풍선 = 결과 `content` 텍스트 첫 줄 + 위젯 카드(`tool-input` → `tool-result`에 **실제 응답**)
  3. "다음 대화" 버튼 → 서연 "예산은 좀 넘어도 돼" → **실제 `tools/call adjust_plan`** `{problem_id: 받은 값, action:{type:"yield",name:"서연",text:"2만원 안으로"}}` → 새 메시지에 새 위젯 카드
  4. 시나리오 토글 "조건 충돌": 민지 "디뮤지엄 꼭 + 공방 14시 꼭", 지훈 "1km 넘게는 못 걸어" → 실제 `propose_plans`(smoke의 `IMPOSSIBLE`과 같은 인자) → infeasible 카드
- 위젯 → 호스트:
  - `tools/call` → **그대로 서버 `/mcp`로 전달**하고 응답을 위젯에 돌려준다(이름은 `adjust_plan`/`explain_infeasible`만 허용, 그 외 거절)
  - `ui/message` → 그 텍스트를 내 말풍선으로 대화에 추가. 텍스트가 대본 규칙에 맞으면 실제 호출로 이어간다: "○○ … 양보할게" → 위젯이 보낸 메시지 안에 함께 온 구조화 정보가 없으므로, 위젯이 `ui/message`를 보내기 직전 화면에 있던 선택지의 `apply` 액션을 호스트가 알 방법이 필요하다 → board.html이 `ui/message` params에 표준 필드 외 `_meta: {"hapui/apply": action}`을 함께 넣게 하고(스펙상 `_meta`는 확장 가능), 호스트는 그 action으로 `adjust_plan` 실제 호출 → 새 카드. "이 안으로 정하기"류는 실제 계산이 필요 없으니 vooy 말풍선 "좋아요, ○○안으로 정할게요. 예약은 vooy가 이어서 도와요(데모 문구)"만
  - `ui/request-display-mode`, `size-changed`, `open-link`는 지금처럼
- 서버 오류·요청 제한(429)·네트워크 실패: vooy 말풍선에 한국어로 무엇이 실패했는지 + 다시 시도 버튼. 위젯은 이전 결과 유지
- 화면 상단 안내 한 줄: "대화는 데모 대본 · 계산과 위젯은 실제 MCP 서버(`/mcp`) 호출" + 마지막 호출의 메서드·소요 ms를 작은 로그 줄로(예: `tools/call propose_plans · 3.9s`). 이건 심사자가 "진짜 호출"임을 확인하는 근거다
- `ui/fixtures/`와 `scripts/make_fixtures.py`는 미리보기에서 더 이상 쓰지 않으면 **삭제**(죽은 코드 금지). 다른 곳에서 쓰면 남기고 이유를 요약에 적어라

## 3. 로컬 확인 (직접 돌려라)

- `.venv/bin/python -m pytest -q` 통과
- `HAPUI_HOST=127.0.0.1 .venv/bin/python -m hapui.server --port 8770` 띄운 뒤 `curl -s http://127.0.0.1:8770/chat | head` 200, `curl`로 `/mcp` `resources/read` 호출해 위젯 HTML이 오는지 확인(포트를 열 수 없는 환경이면 Starlette TestClient로 같은 확인을 테스트로)
- 보안 grep 0건: `grep -nE "innerHTML\s*=\s*[^'\"\`]|eval\(|new Function|on[a-z]+=\"" ui/board.html ui/chat.html`

## 4. 지켜야 할 것

- 07의 TripFit 벤토 카드 디자인·채팅 맥락 설계는 그대로 유지
- 건드리지 마라: `Dockerfile`, 루트 `README.md`, `PRD.md`, `IDEAS.md`, 상위 폴더, `.env`. `hapui/`는 server.py(경로 추가)와 꼭 필요한 최소 수정만
- 공개 서버 주소를 코드에 박지 마라. 미리보기는 항상 자기 출처의 `/mcp`를 부른다

## 5. 문구 규칙 (사용자 규칙, 반드시)

화면에 보이는 모든 문구(`ui/chat.html`, `ui/board.html`)와 도구 결과 텍스트(`hapui/text.py`의 content)에서 **줄표(—, –)와 가운데 점(·)을 쓰지 않는다.** 나열은 쉼표, 문장 연결은 마침표나 괄호, 숫자 범위는 물결표(13:00~18:00), 화면의 메타 줄("성수 13:00~18:00 3명 4곳")은 글자 구분 기호 대신 CSS `gap`으로 띄운 별도 span. 이 브리프 안의 예시 문구에 ·나 —가 있으면 이 규칙으로 바꿔서 써라(예: "TripFit · propose_plans · 3.9초" → "TripFit propose_plans 3.9초"를 span 간격으로). 기존 `board.html`·`text.py`에 남아 있는 것도 이번에 모두 바꾸고, 테스트가 그 기호에 의존하면 같이 고쳐라. 확인: `grep -nE "·|—|–" ui/board.html ui/chat.html hapui/text.py` 0건(주석 포함).

## 끝에 남길 요약

바뀐 파일, 브라우저 MCP 클라이언트가 보내는 요청 순서, 위젯 HTML을 어떻게 받아 어떻게 띄웠는지(CSP 처리 포함), 지운 파일, 테스트 수, 확인 못 한 것
