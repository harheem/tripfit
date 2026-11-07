# 01 — 합의저울 원격 MCP 서버 (vooy용)

너는 `vooy-mcp/` 폴더에서 일한다. 해커톤 vooy 트랙 제출물이고, **실제 사람들이 메신저(vooy)에서 아무렇게나 쓴다**고 가정한 견고하고 안전한 서버가 필요하다. 먼저 이 문서들을 끝까지 읽어라:

- `PRD.md` — 계약의 기준. 특히 §3(도구 계약·structuredContent 모양), §4(공개 기본값표), §5(견고성), §6(보안), §8(구조), §9(완료 기준)
- `IDEAS.md` §4.1(무대 시나리오)
- 솔버 원본(읽기 전용): `../tripfit/solver/tripfit_solver.py`, `../tripfit/solver/sample_seongsu.py`, `../tripfit/solver/demo.py`, `../tripfit/solver/test_solver.py`

## 만들 것 (PRD §8 구조에서 `ui/` 제외 전부)

1. `hapui/engine/tripfit_solver.py` — 원본을 **복사**하고 맨 위에 출처 주석. 수학은 그대로 두되 PRD가 요구하는 두 제약만 추가: `budget`(Σ 1인 가격 ≤ 상한), `eat_by`(식당 1곳이 그 시각 전에 시작). 3인 이상에서 `alternatives`가 PRD §4 "3안" 규칙대로 나오게 래퍼(`planner.py`)에서 조립해도 된다. `_quiet_native_stdout`은 유지.
2. `hapui/engine/places_seongsu.py` — 샘플 복사 + **식당 4곳 추가**(성수 실재하는 동네 식당 느낌의 일반 이름으로, 좌표는 성수역 반경 800m 근사, `source="sample"`). 실제 상호를 지어내지 말고 "성수 국밥집(샘플)"처럼 샘플임이 드러나게.
3. `hapui/schema.py` — pydantic v2 입력·출력 모델. PRD §3.1 입력을 **관대하게** 받는다: `strength` 강/보통/약/strong/normal/weak/없음, 시간 "15:00"/"15시"/"오후 3시"/"3pm", 금액 20000/"2만원"/"2만", `kind` 모르는 값 → `other`. 한도(인원 8, 말 8, 글자 200, 후보 40, 창 1~12시간)는 잘라서 처리하고 경고로 돌려준다. 제어문자·양방향 제어문자(U+202A–202E, U+2066–2069) 제거.
4. `hapui/mapping.py` — wants → 솔버 `Pref`/`Request` 하드 제약. PRD §4 표를 **상수 하나**로 두고 README에도 그대로 쓸 수 있게 `PUBLIC_DEFAULTS` dict로 export.
5. `hapui/planner.py` — `propose(input) -> result`, `adjust(problem_id, action)`, `explain(problem_id)`. 불가능하면 자동으로 diagnose해서 `concessions` 채움(사람 이름을 붙인 형태, `apply` 액션 포함). 솔버는 **전역 `threading.Lock`으로 직렬화**(대기 8초 넘으면 `busy`), 솔버 time_limit 3초, 해가 없으면 탐욕 휴리스틱 폴백(`flags:["근사해"]`). 후보가 40곳 넘으면 말과의 관련도 + Q로 25곳까지 줄인다.
6. `hapui/store.py` — problem 저장(메모리, TTL 6시간, LRU 500, `rev`, undo 스택 10). `problem_id`와 `board_token`은 서로 다른 `secrets.token_urlsafe(24)`.
7. `hapui/mrt.py` — `https://mcp-servers.myrealtrip.com/mcp` 고정 주소 JSON-RPC 클라이언트(`tools/call searchTnas {"query": "서울 성수 공방"}` 형태, 응답이 SSE `data:` 줄로 올 수도 있음). 타임아웃 5초, 응답 1MB 상한, 실패하면 예외 대신 `None`. **사용자 입력 URL은 절대 열지 않는다.** 테스트에서는 네트워크를 쓰지 말고 mock.
8. `hapui/text.py` — `content` 텍스트 렌더(PRD §3.1 텍스트 규칙: 12줄 이내, 메신저에 그대로 붙여도 읽힘, 이름은 따옴표, 데이터 라벨, 보드 링크).
9. `hapui/server.py` — mcp **2.3.0** SDK(이미 `vooy-mcp/.venv`에 설치됨. FastMCP가 아니라 `from mcp.server.mcpserver import MCPServer`, MCP Apps는 `from mcp.server.apps import Apps, client_supports_apps`. 사용법은 `.venv/lib/python3.11/site-packages/mcp/server/apps.py` docstring과 소스를 읽어라).
   - 도구 4개(`propose_plans`, `adjust_plan`, `explain_infeasible`, `find_candidates`). 앞 3개는 `_meta.ui.resourceUri = "ui://hapui/board.html"`, `adjust_plan`은 visibility `["model","app"]`. `find_candidates`는 UI 없음.
   - 도구 설명: 한국어 예문 5개 + 영어 한 줄. 입력 스키마의 각 필드에 description(예시 포함) — vooy LLM이 이것만 보고 채운다.
   - 결과: `content`(text.py) + `structuredContent`(PRD §3.1 모양, `v: 1`). 오류도 `isError: true` + 한국어 `{code, message, field, hint}`.
   - UI 리소스 `ui://hapui/board.html`: `ui/board.html` 파일을 읽어 서빙(MIME `text/html;profile=mcp-app`). 파일이 아직 없으면 최소 placeholder HTML. 파일 안 `<!--HAPUI_BOOT-->` 자리에 `<script id="hapui-boot" type="application/json">{"mode":"app"}</script>`를 넣어 준다. **`ui/board.html`은 다른 작업자가 동시에 만들고 있으니 수정하지 마라.**
   - HTTP: `streamable_http_app(stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(...))`를 Starlette 앱에 마운트(`/mcp`). 같은 앱에 `GET /healthz`, `GET /b/{token}`(board.html + `<!--HAPUI_BOOT-->` 자리에 `{"mode":"web","token":…}` JSON, `</`는 `<\/`로 이스케이프, CSP nonce를 `__CSP_NONCE__` 자리에 치환), `GET /api/board/{token}`, `POST /api/board/{token}/adjust`(body는 adjust_plan의 action).
   - 보안(PRD §6 표 전부): `allowed_hosts`에 localhost·127.0.0.1·`HAPUI_PUBLIC_HOST`(ngrok 호스트, 있을 때), `HAPUI_TOKEN`이 있으면 `/mcp`에 Bearer 필수(`/b`, `/api/board`는 board_token으로만), IP별 분당 60 요청·솔버 분당 20 제한(메모리 토큰 버킷), 본문 64KB, 보드 응답 보안 헤더(CSP·Referrer-Policy·nosniff·frame-ancestors none). 로그에 사람 말·이름 금지.
   - `board_url`은 `HAPUI_PUBLIC_URL` 환경 변수가 있을 때만 채운다(없으면 `http://127.0.0.1:<port>`).
   - CLI: `python -m hapui.server --port 8765 [--stdio]`. stdio 모드에서는 stdout을 JSON-RPC 전용으로 두고 로그는 stderr.
   - `.env`는 상위 폴더(`vooy-mcp/../.env`)에서 python-dotenv로 읽되 이 서버는 키가 필요 없다. 키 값을 어디에도 쓰지 마라.
10. `scripts/smoke_mcp.py <url>` — 공식 SDK 클라이언트(`mcp` 2.3의 streamable HTTP client)로 initialize → tools/list → `propose_plans`(IDEAS §4.1 3인 시나리오) → `adjust_plan(yield 서연 2만원)` → 불가능 시나리오(민지: 디뮤지엄 꼭 + 공방 14시 꼭 + 지훈 걷기 1km 하드) → 이상 입력 6종(빈 members, 이름 중복·이모지, `kind:"순간이동"`, 창 끝<시작, 1000자 말, `<img src=x onerror=alert(1)>` 이름). 각 단계 결과 텍스트 앞 3줄과 ms를 출력.
11. `tests/` — pytest: 정규화(시간·금액·강도), 한도 자르기, 오류 모양, `other` 강등, 불가능 → concessions, adjust rev/undo, 토큰 만료·없는 토큰 404, 동시 `propose` 10개(스레드)가 모두 성공하거나 `busy`로 끝남(크래시 없음), XSS 이름이 `/b/` HTML 본문에 날것으로 박히지 않음(JSON boot 안에서 이스케이프), Host 헤더 차단, Bearer 동작. 네트워크 금지(MRT mock).
12. `requirements.txt` — 실제로 쓴 패키지만(`mcp==2.3.0`, `mip==1.16rc0`, `python-dotenv`, `httpx`, `uvicorn`, `pytest` …).

## 규칙

- Python은 `vooy-mcp/.venv/bin/python`. 새 패키지가 필요하면 쓰지 말고 결과 요약에 적어라(네트워크가 막혀 있을 수 있다).
- 건드리면 안 되는 것: `vooy-mcp/ui/`(다른 작업자), `vooy-mcp/PRD.md`·`IDEAS.md`, 상위 폴더의 `tripfit/`·`skt-agentic-pay/`·`fnf-vmd/`, `.env`.
- 실호출 vs 샘플: 결과의 `data_labels`와 각 stop의 `source`로 항상 구분. 샘플 데이터를 실데이터처럼 쓰지 마라.
- CBC는 stdout에 찍는다. 솔버 호출은 항상 `_quiet_native_stdout` 안에서, 그리고 락 안에서.

## 완료 확인 (직접 돌려라)

```bash
cd vooy-mcp
.venv/bin/python -m pytest -q
.venv/bin/python -m hapui.server --port 8765 &   # 끝나면 종료
.venv/bin/python scripts/smoke_mcp.py http://127.0.0.1:8765/mcp
curl -s http://127.0.0.1:8765/healthz
```

## 끝에 남길 요약 (결과 파일)

1. 바뀐/만든 파일 목록
2. 실행 방법
3. pytest 결과 숫자, smoke 출력 요약(3인 시나리오 3안의 사람별 %와 solve_ms, 불가능 시나리오 concessions)
4. 남은 목업·샘플
5. 확인 못 한 것, PRD와 다르게 한 것과 이유
