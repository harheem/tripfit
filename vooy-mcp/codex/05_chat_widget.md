# 05 — 대화창 안 위젯 최적화 (MCP Apps inline 카드) + 메신저 미리보기 호스트

너는 `vooy-mcp/` 폴더에서 일한다. `ui/board.html`은 지금 **전체 페이지형 보드**다(폰 폭에서 높이 약 2,600px). 이 화면이 **실제 단톡방 대화 흐름 안**에 MCP Apps 위젯으로 뜬다고 가정하고 다시 설계한다. 말풍선 사이에 2,600px짜리 페이지가 끼면 대화가 망가진다.

먼저 읽어라: `PRD.md` §3.1(structuredContent 계약), §6(보안), §7(화면), `ui/README.md`, 지금 `ui/board.html`, MCP Apps 요점(아래).

## MCP Apps 요점 (스펙 2026-01-26)

- 뷰→호스트 요청: `ui/initialize`, `tools/call`, `ui/open-link {url}`, `ui/request-display-mode {mode: "inline"|"fullscreen"|"pip"}`(응답에 실제 적용된 mode), `ui/message`
- 뷰→호스트 알림: `ui/notifications/initialized`, `ui/notifications/size-changed {width,height}`
- 호스트→뷰 알림: `ui/notifications/tool-input`, `ui/notifications/tool-result`(CallToolResult), `ui/notifications/tool-cancelled`, `ui/notifications/host-context-changed`
- `hostContext`: `theme`(light|dark), `displayMode`, `availableDisplayModes`(있을 수도 없을 수도), `containerDimensions`(maxWidth/maxHeight 등, 없을 수도), `safeAreaInsets`, `styles.variables`(예: `--color-background-primary`, `--color-text-primary`, `--font-sans`, `--border-radius-md`), `locale`, `platform`

## 1. 두 가지 표시 모드

| 조건 | 화면 |
|---|---|
| App 모드 + `displayMode` inline(기본) | **대화 카드**(아래 §2). 새로 만든다 |
| App 모드 + fullscreen, 그리고 Web(`/b/<token>`)·Demo 모드 | 지금의 **전체 보드**를 그대로(디자인 유지, 회귀 금지) |

`host-context-changed`로 모드가 바뀌면 그 자리에서 전환한다. 같은 상태(state)를 두 화면이 공유한다.

## 2. 대화 카드 (inline) 설계

메신저 대화창 안 말풍선 줄에 들어가는 카드다. 실제로 사람들은 **폰으로 단톡방을 스크롤하다** 이 카드를 본다.

- **폭**: 유동 260~420px. 300px와 360px에서 완성도를 맞춰라. 가로 스크롤 금지
- **높이**: inline에서 **최대 440px, 목표 360~400px**. 카드 안 스크롤 금지(넘치면 요약해서 줄이고 "+N"으로)
- **바탕**: 페이지 전체를 네이비로 칠하지 마라. 문서 배경은 투명, 카드 하나(라운드 20px, 1px 옅은 테두리)가 메신저 배경(라이트면 옅은 회청색, 다크면 짙은 남색) 위에 떠 있는 느낌. 라이트 기본 카드 면은 흰색 계열, 다크 테마면 짙은 면. 파스텔 벤토는 **카드 안의 작은 블록**에만(사람 색 점·막대·안 탭)
- **내용 순서**
  1. 머리줄: 작은 브랜드 마크 + "TripFit for vooy", 오른쪽에 알약 "3안 · 4.2초"(solve_ms) — 한 줄
  2. 제목: "성수 13:00–18:00 · 3명" (area/window/members)
  3. 안 선택: 알약 3개(균형 / ○○ 우선…), 선택은 라임. 이름이 길면 말줄임
  4. 사람 줄: 사람마다 **한 줄**(색 점 · 이름 · 얇은 막대 · % 숫자 22~26px · 항목 요약 "✓2 ◐1"). 최대 4명 보이고 나머지는 "+N명". `pct: null`이면 "조건 없음"
  5. 코스 줄: 세로 미니 타임라인 최대 4곳(시각 · 장소명 한 줄, 출처가 샘플이면 작은 "샘플" 배지), 넘치면 "+N곳"
  6. 상태 줄(있을 때만 한 줄): "확인 못 한 말 1개" / "바뀐 점: 카페 1곳 들어옴 · 골목 1곳 빠짐"(diff) / "근사해"
  7. 버튼 줄: **[크게 보기]** **[되돌리기]**(undo 가능할 때만). 크게 보기 = `ui/request-display-mode {mode:"fullscreen"}` → 거절되거나 `availableDisplayModes`에 fullscreen이 없으면 `board_url`이 있을 때 `ui/open-link`, 둘 다 안 되면 버튼 숨김
  8. 맨 아래 아주 작은 데이터 라벨: "실제 계산 · 장소 샘플(성수) · 도보 추정"
- **불가능(infeasible)일 때**: 머리줄 아래 빨강 계열 띠 "이대로는 안 돼요 — 하나만 양보하면 돼요", 양보 선택지 최대 3줄(누가 · 무엇을 · 그러면 최소 N%) + 각 줄 [이걸로] 버튼(= 그 선택지의 `apply`로 `tools/call adjust_plan`). 코스 줄 대신
- **need_candidates / 오류**: 한두 줄 안내 + 무엇을 하면 되는지
- **양보 버튼**: inline 카드에는 항목별 양보 버튼을 두지 않는다(대화로 "그건 양보할게"라고 말하면 vooy가 `adjust_plan`을 부르고 새 tool-result로 카드가 갱신됨). 사람 줄을 탭하면 그 사람 항목이 아래로 펼쳐지는 정도는 허용(높이 한도 지킬 것)
- **글자**: 본문 14px, 보조 12~13px(이보다 작게 금지), 한글 line-height 1.4, 대비 4.5:1. 버튼 높이 40px 이상
- **호스트 스타일**: `styles.variables`가 있으면 폰트·배경·글자색·라운드를 그 값으로(없으면 기본값). `safeAreaInsets` 반영

## 3. 대화 속 모션 (짧고 조용하게)

- 첫 등장: 카드 전체가 8px 아래에서 페이드 업 200ms. 내부 순차 등장 없음(대화에 끼는 카드는 요란하면 안 됨)
- 새 tool-result(다른 사람 말로 재계산): 막대 `scaleX` 스프링 300ms, % 숫자 롤링, 코스 줄 FLIP(들어온 곳은 짧은 하이라이트, 빠진 곳은 접히며 사라짐), 상태 줄에 diff 문구
- 계산 중(`tool-input`·`tools/call` 대기): 머리줄 알약이 "계산 중…" 점 3개로, 나머지는 이전 결과 유지(빈 카드 금지)
- 높이가 바뀌면 `size-changed`를 보내되 애니메이션 중엔 프레임마다 보내지 말고 끝난 뒤 한 번(+ ResizeObserver 디바운스 50ms)
- `prefers-reduced-motion`: 전부 즉시

## 4. 메신저 미리보기 호스트 `ui/preview.html` (새 파일, 개발·README 스크린샷용)

실제 MCP Apps 호스트처럼 `board.html`을 iframe에 띄우고 브리지를 구현해서, 대화 흐름 안에서 카드를 검증하는 페이지다. **특정 메신저 상표(카카오톡 이름·로고·노란 말풍선 등)를 흉내 내지 마라.** 일반적인 단톡방 모양(회청색 배경, 원형 이니셜 아바타, 흰 말풍선, 내 말풍선은 옅은 라임)으로.

- 폰 프레임 폭 390px(토글 320/390), 라이트/다크 토글, 시나리오 토글(정상 / 불가능)
- 대화 대본(위에서 아래로): 민지 "난 전시 하나는 꼭" → 지훈 "많이 걷기 싫어. 3시 전엔 밥" → 서연 "카페에서 좀 쉬고 싶고 2만원 안으로" → 서연 "@vooy 성수 1시부터 6시까지 코스 짜줘" → vooy 말풍선(결과 `content` 텍스트 앞 3줄) + **위젯 iframe** → 서연 "예산은 좀 넘어도 돼" → vooy "다시 계산했어요" + 같은 위젯이 새 tool-result로 갱신(새 iframe을 만들지 말고 기존 카드에 두 번째 결과를 보냄)
- iframe: `board.html`을 fetch해 `<!--HAPUI_BOOT-->`를 `<script id="hapui-boot" type="application/json">{"mode":"app"}</script>`로, `__CSP_NONCE__`를 임의 값으로 치환해 `srcdoc`, `sandbox="allow-scripts"`(allow-same-origin 금지)
- 호스트 브리지(postMessage JSON-RPC 2.0, `event.source === iframe.contentWindow`만 처리):
  - `ui/initialize` → `{protocolVersion:"2026-01-26", hostInfo:{name:"preview-host",version:"0.1"}, hostCapabilities:{}, hostContext:{theme, displayMode:"inline", availableDisplayModes:["inline","fullscreen"], containerDimensions:{maxWidth: 말풍선 폭}, locale:"ko-KR", platform:"mobile"}}`
  - `ui/notifications/initialized` 받으면 `tool-input` → 600ms 뒤 `tool-result`
  - `ui/notifications/size-changed` → iframe 높이 반영
  - `ui/request-display-mode` → fullscreen이면 폰 프레임을 덮는 오버레이로 iframe을 옮기고(또는 크기 확대) `host-context-changed {displayMode:"fullscreen"}`; 닫기 버튼으로 inline 복귀
  - `tools/call adjust_plan` → 미리보기에는 계산 서버가 없으니 다음 fixture 상태로 응답(`{structuredContent, content}`), 없으면 JSON-RPC error
  - `ui/open-link` → `window.open`(noopener)
- 데이터: **실제 서버 결과**를 fixture로 쓴다. `scripts/smoke_result_remote.json`(공개 Lightsail 서버 실행 결과)의 `3인 시나리오`, `서연 예산 양보`, `불가능 시나리오` 호출의 `result`(structuredContent)와 텍스트를 뽑아 `ui/fixtures/real_propose.json`, `real_yield.json`, `real_infeasible.json`으로 저장(뽑는 스크립트 `scripts/make_fixtures.py`도 남겨라). `board_url`은 그대로 두되 미리보기 화면에는 "만료될 수 있는 링크"로만 쓴다
- 미리보기 상단에 작은 안내: "MCP Apps 호스트 미리보기 · 실제 서버 결과(장소는 성수 샘플)"

## 5. 지켜야 할 것

- 보안 규칙 그대로: 데이터는 `textContent`/`setAttribute`만, `innerHTML`에 데이터 금지, `eval`·`new Function`·인라인 이벤트 속성 금지, 외부 리소스 0개, 스크립트 태그는 `nonce="__CSP_NONCE__"` 하나(preview.html은 서버가 서빙하지 않으니 일반 스크립트 1개면 됨)
- Web(`/b/<token>`) 모드·전체 보드의 기존 동작 회귀 금지
- 건드리지 마라: `hapui/`, `tests/`, `Dockerfile`, `PRD.md`, `IDEAS.md`, `README.md`(루트), 상위 폴더, `.env`
- 테스트: `.venv/bin/python -m pytest -q`가 계속 통과(54개). `grep -nE "innerHTML\s*=\s*[^'\"\`]|eval\(|new Function|on[a-z]+=\"" ui/board.html ui/preview.html` 0건. `node --check`가 있으면 추출한 스크립트로 구문 검사

## 끝에 남길 요약

바뀐/만든 파일, 대화 카드 레이아웃(300/360px에서 예상 높이), 모드 전환 방식, 모션 목록, 미리보기 실행법(`cd ui && python3 -m http.server 8791` → `/preview.html`), 확인 못 한 것
