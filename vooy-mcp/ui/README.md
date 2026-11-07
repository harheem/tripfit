# TripFit 채팅 카드와 전체 보드

`board.html`은 App inline에서 네이비 벤토 카드, App fullscreen과 Web(`/b/<token>`)에서 전체 보드를 표시한다. 카드 디자인, 파스텔 타일, 안 선택, 숫자 모션과 전체 보드의 저울은 유지한다. 외부 폰트, 이미지, 라이브러리는 로드하지 않는다.

## 공개 대화 데모

프로젝트 루트에서 실행한다.

```sh
HAPUI_HOST=127.0.0.1 .venv/bin/python -m hapui.server --port 8770
```

`http://127.0.0.1:8770/chat`을 연다. 공개 배포에서도 같은 서버의 `/chat` 링크를 사용한다. `/preview` 경로와 로컬 fixture 미리보기는 없다. `/chat`은 데이터 없는 정적 페이지이며 인증 없이 열린다. `/mcp`는 기존 Guard의 Host, Origin, 선택적 Bearer, 요청 제한을 그대로 따른다. 공개 데모 배포는 익명 MCP 호출이 가능한 기존 서버 설정을 사용한다.

- **시작**: 민지, 지훈, 서연의 대본을 0.8초 간격으로 재생한 뒤 실제 코스를 계산한다.
- **다음, 서연 예산 빼기**: `adjust_plan`으로 예산 조건을 풀고 새 메시지에 새 카드를 붙인다.
- **조건 충돌 시나리오**: `scripts/smoke_mcp.py`의 `IMPOSSIBLE`과 같은 인자로 계산한다. 카드의 빼기 선택지도 실제 재계산으로 이어진다.
- **직접 입력**: `@TripFit`과 `짜줘`, `정해줘`, `코스` 중 하나가 있으면 현재 대본 인자로 호출한다. 이름과 `빼도`, `넘어도`, `괜찮아`, `다음에` 또는 기존에 맞춰 주겠다는 표현이 있으면 이번엔 빼기(`yield`)로 첫 번째 want를 빼고, 예산을 명시하면 budget want를 선택한다. 자유로운 자연어 해석이나 LLM 호출은 하지 않는다.
- **단톡 라이트 / DM 다크**: 기존 스킨을 전환한다. 카드 폭은 폰 폭의 72%, 최대 340px이다.

상단에 데모의 범위와 실제 호출 여부를 표시한다. 기술 정보에는 최근 10개 요청의 메서드, 도구, 실제 왕복 ms, HTTP 상태와 마지막 도구 인자 JSON이 남는다. 네트워크 실패, 서버 오류, HTTP 429는 한국어 말풍선과 다시 시도 버튼으로 표시한다. 기존 카드는 유지한다. 시간 초과 뒤 수동 재시도는 이미 반영된 요청을 다시 적용할 수 있으므로 화면에 이를 안내한다.

## MCP 클라이언트와 Apps 호스트

첫 계산의 요청 순서는 다음과 같다.

1. `initialize` (`2025-06-18`, `capabilities.extensions["io.modelcontextprotocol/ui"].mimeTypes`)
2. `notifications/initialized`
3. `tools/list`
4. `propose_plans._meta.ui.resourceUri`를 사용한 `resources/read`
5. `tools/call propose_plans`

모든 요청은 같은 출처의 `/mcp`로 보낸다. JSON 응답과 SSE `data:` 이벤트를 파싱한다. 위젯은 MIME `text/html;profile=mcp-app`를 확인한 서버 HTML만 사용한다. HTML을 DOMParser로 읽어 모든 script의 nonce를 `/chat`의 nonce로 맞춘 뒤 `sandbox="allow-scripts"` iframe의 `srcdoc`에 넣는다. `allow-same-origin`은 사용하지 않는다. iframe은 부모 CSP를 상속한다. 부모는 nonce 스크립트, 인라인 스타일, 같은 출처 연결과 프레임만 허용한다.

위젯 초기화 뒤 호스트가 실제 인자를 `ui/notifications/tool-input`, 실제 MCP 결과 전체를 `ui/notifications/tool-result`로 전달한다. 새 계산의 공유 메시지는 새 iframe을 만든다. 이전 카드의 선택과 결과는 유지한다.

위젯의 `tools/call`은 `adjust_plan`, `explain_infeasible`만 허용하고 해당 카드의 problem_id를 검사한 뒤 실제 서버에 전달한다. 성공과 도구 오류 응답은 위젯에 돌려준다. 직접 도구 조작은 요청한 카드만 갱신한다.

빼기와 되돌리기는 `ui/message`에 사용자 문구와 `_meta: {"hapui/apply": action}`을 함께 보낸다. 호스트는 해당 카드의 problem_id와 action(두 조건을 함께 푸는 `also` 포함)으로 재계산하고 새 카드를 추가한다. 호스트가 메시지를 명시적으로 거절할 때만 위젯이 기존 도구 호출로 대체한다. 메시지 시간 초과는 자동 재호출하지 않는다.

안 확정은 계산 없이 대화에 예약 안내 데모 문구만 남긴다. 실제 예약 도구는 없다. 확대는 `ui/request-display-mode`, 웹 보드는 `ui/open-link`를 사용한다. 닫기와 Escape는 같은 iframe과 대화 스크롤을 복원한다. 메시지의 source가 등록된 iframe인지 검사한다.

## 독립 보드와 검증

`sample_state.json`, `sample_state_infeasible.json`은 `board.html`의 독립 Demo 모드에서만 사용한다. `/chat`은 이 파일들을 읽지 않는다. `ui/fixtures/`와 `scripts/make_fixtures.py`는 삭제했고 텍스트 테스트도 실제 planner 결과를 사용한다.

`.venv/bin/python -m pytest -q`로 서버, 보드, MCP와 텍스트 계약을 검증한다. `tests/test_chat.py`는 정적 페이지 보안 헤더, 잘못된 Host, 기존 요청 제한, 실제 초기화/리소스/계산/빼기/충돌 해결 교환, 대본 인자 일치와 금지 문구를 확인한다.

현재 작업 환경은 TCP 포트 열기와 Chrome 실행/접근을 허용하지 않아 실제 브라우저 CSP와 시각 검증은 완료하지 못했다. TestClient 검증은 HTTP 소켓을 사용하지 않는다. 배포 전 `/chat`에서 카드가 표시되고 확대 및 빼기가 동작하는지 실제 브라우저로 확인해야 한다.
