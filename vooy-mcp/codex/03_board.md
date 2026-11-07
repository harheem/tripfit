# 03 — 합의저울 보드 화면 (MCP App 위젯 = 웹 보드, HTML 파일 하나)

너는 `vooy-mcp/` 폴더에서 일한다. 메신저(vooy) 안 MCP App 위젯과, 같은 화면을 웹 링크(`/b/<token>`)로 여는 보드를 **한 HTML 파일**로 만든다. 실제 사람들이 폰에서 누르고 미는 화면이고, 해커톤 무대(1분 데모)에서 보여 줄 장면이다. 레이아웃·애니메이션·견고함·보안 모두 중요하다.

먼저 읽어라:
- `PRD.md` §3.1(structuredContent 계약 — 화면은 이것만 믿는다), §3.2(adjust 액션), §3.3(concessions), §6(보안: 위젯·보드 행), §7(화면·모션 전부)
- 디자인 원본(읽기 전용): `../tripfit/SCREENS.md` §3(벤토 모자이크 규칙), `../tripfit/web/index.html`(같은 스타일로 만든 프로토타입. CSS 스프링 `linear()`, 숫자 롤링, 다이내믹 아일랜드 구현을 참고해 가져와도 된다)

## 만들 것

1. `ui/sample_state.json` — PRD §3.1 모양 그대로, 3인(민지·지훈·서연) 성수 13:00–18:00 시나리오. 3안, `unmapped` 1개("재밌게 놀자"), `data_labels`. 두 번째 파일 `ui/sample_state_infeasible.json`(status infeasible, concessions 3개).
2. `ui/board.html` — 외부 리소스 0개(폰트·스크립트·이미지·아이콘 전부 인라인 SVG/CSS). 파일 하나로 끝.

### 모드 판별 (`<!--HAPUI_BOOT-->` 자리에 서버가 `<script id="hapui-boot" type="application/json">…</script>`를 넣는다)

- `{"mode":"app"}` → **App 모드**: MCP Apps 스펙(2026-01-26) postMessage JSON-RPC 2.0. 직접 구현한다(번들러·npm 없이):
  - `window.parent`에 요청 `ui/initialize` `{protocolVersion:"2026-01-26", appInfo:{name:"hapui-board",version:"0.1"}, appCapabilities:{}}` → 응답의 `hostContext`(`theme` light|dark, `displayMode`, `safeAreaInsets`{top,right,bottom,left}, `styles.variables`, `containerDimensions`) 반영 → 알림 `ui/notifications/initialized`
  - 호스트→뷰 알림: `ui/notifications/tool-input`(계산 중 표시), `ui/notifications/tool-result`(params가 CallToolResult. `structuredContent`로 렌더), `ui/notifications/tool-cancelled`, `ui/notifications/host-context-changed`
  - 뷰→호스트 요청: `tools/call` `{name:"adjust_plan", arguments:{problem_id, action}}` → 응답의 `structuredContent`로 다시 렌더. 실패하면 이전 화면 유지 + 아일랜드에 오류
  - 크기: `ResizeObserver`로 문서 높이가 바뀌면 `ui/notifications/size-changed` `{width,height}`
  - 링크 열기는 `ui/open-link` `{url}`(보드 링크 버튼)
  - 메시지는 `event.source === window.parent`인 것만 받는다. id별 대기 Promise, 10초 타임아웃
- `{"mode":"web","token":"…"}` → **Web 모드**: `GET /api/board/<token>` → 렌더, 조작은 `POST /api/board/<token>/adjust`(body = action JSON). 404/410이면 "링크가 만료됐어요" 화면
- boot가 없고 iframe이 아니면 → **Demo 모드**: `sample_state.json`을 fetch(로컬 `python -m http.server`로 확인). `?infeasible=1`이면 다른 샘플. Demo 모드의 adjust는 화면에서 그럴듯한 가짜 diff를 만들지 말고, 미리 준비한 두 번째 상태로 바꾸거나 "데모 모드: 계산 서버 없음" 표시

### 레이아웃 (PRD §7 순서, 모바일 먼저 320~480px에서 완성, 640px 이상이면 사람 막대·타임라인 2열)

아일랜드 → 안 탭 → 사람 막대(색 블록, 큰 % 숫자, 체크리스트 항목 상태 아이콘 ✓◐✕⤺?, 항목별 "양보" 알약) → 저울(사람별 슬라이더, 놓을 때만 400ms 디바운스로 `weights` 액션) → 타임라인(시각·체류·다음까지 도보 m·출처 배지 "샘플"/"실호출"/"vooy") → 양보 카드(infeasible일 때, 적용 버튼 = 그 카드의 `apply` 액션) → `unmapped`("확인할 수 없는 말" 블록, 원문 인용) → 바닥 데이터 라벨. "되돌리기" 버튼(`undo`). 웹 링크 버튼(App 모드에서 `board_url`이 있을 때).

- 벤토 규칙: 네이비 바탕, 블록 사이 4px 틈, 단색 파스텔(라임 = 합의/선택, 사람 색은 `members[].color`: pink·sky·peach·butter·mint·lilac), 빨강 = 문제. 그라데이션 금지(하단 페이드 1개만 허용). 숫자는 크게(사람 % 56px 이상), 위계는 크기로
- 폰트: `-apple-system, "Apple SD Gothic Neo", "Pretendard", system-ui, sans-serif`. 숫자 `font-variant-numeric: tabular-nums`
- 다크: `hostContext.theme === "dark"` 또는 `prefers-color-scheme: dark`면 바탕만 더 깊게, 블록 채도 유지, 글자 대비 4.5:1
- `safeAreaInsets`를 padding으로. 가로 스크롤 금지. 긴 이름·긴 장소명은 말줄임 + `title`
- 버튼 44px 이상, 슬라이더 키보드 조작, 아일랜드 `aria-live="polite"`, 상태 아이콘에 텍스트 대체

### 모션 (PRD §7.1 표 전부)

첫 등장 순차 스프링 / % 숫자 자리별 롤링 / 막대 `scaleX` 스프링 / 타임라인 FLIP(남는 카드 이동, 새 카드 아래에서 튀어 오름, 빠지는 카드 기울며 왼쪽 퇴장) / 아일랜드 펼침 / 양보 누르면 항목 접힘 + 다른 사람 막대 상승 동시. `transform`·`opacity`만, 400ms 이내, `prefers-reduced-motion`이면 즉시. 재계산 중엔 이전 결과 유지 + 아일랜드 스피너(빈 화면 금지). 같은 상태로 다시 렌더해도 깜빡이지 않게 키(place_id, name) 기준 diff 렌더.

### 보안·견고성

- 사용자·장소 문자열은 전부 `textContent`/`setAttribute`로만. `innerHTML`에 데이터 금지(정적 마크업 템플릿만 허용)
- 계약 필드가 빠지거나 타입이 달라도 죽지 않는다: 각 블록을 방어적으로 렌더하고, 모르는 `v`면 "새 버전 화면이 필요해요"
- `eval`·`new Function`·인라인 이벤트 속성(`onclick=`) 금지. 스크립트 태그는 `<script nonce="__CSP_NONCE__">` 하나(서버가 치환)
- 연타 방지: 요청 중엔 버튼 비활성, 마지막 요청만 반영(rev 비교)

## 건드려도 되는 곳 / 안 되는 곳

- 만들 파일: `ui/board.html`, `ui/sample_state.json`, `ui/sample_state_infeasible.json`, 필요하면 `ui/README.md`(모드·계약 메모)
- 건드리지 마라: `hapui/`, `tests/`, `scripts/`(다른 작업자가 동시에 서버를 만들고 있다), `PRD.md`, `IDEAS.md`, 상위 폴더 전부, `.env`

## 완료 확인 (직접 돌려라)

```bash
cd vooy-mcp/ui && python3 -m http.server 8790   # 확인 후 종료
# 브라우저 없이도: HTML 파서로 구조 점검, 금지 패턴 grep
grep -nE "innerHTML\s*=\s*[^'\"\`]|eval\(|new Function|on[a-z]+=\"" board.html   # 데이터 innerHTML·eval·인라인 핸들러 0건이어야 함
grep -nE "https?://" board.html                                               # 외부 URL 0건(주석 제외)
```

가능하면 headless 브라우저가 있으면 390×844로 Demo 모드 스크린샷을 `ui/_shots/`에 남겨라(없으면 생략하고 요약에 적기).

## 끝에 남길 요약 (결과 파일)

1. 만든 파일, 2. 세 모드 확인 방법, 3. 구현한 모션 목록, 4. 계약에서 애매했던 필드와 어떻게 처리했는지, 5. 확인 못 한 것(특히 실제 MCP Apps 호스트에서의 핸드셰이크)
