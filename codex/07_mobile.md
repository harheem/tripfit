# 07 — 휴대폰에서 열면 앱 화면만 꽉 차게

너는 `tripfit/` 폴더에서 일한다. `web/index.html`은 발표용 레이아웃이다: 가운데 폰 목업(`.phone` 계열), 왼쪽 캡션(`.cap`), 오른쪽 엔진 패널(`.engine`), 하단 키 안내. 17:00–18:00 피플스 초이스 투표 때 참가자들이 **휴대폰으로 데모 링크를 연다.** 지금은 `@media` 대응이 없어 휴대폰에서 깨진다. 데스크톱 발표 화면은 한 픽셀도 바뀌면 안 된다.

## 할 일 (`web/index.html`만)

1. **모바일 모드** — `(max-width: 700px)` 또는 `(pointer: coarse) and (max-width: 900px)`일 때 `body.mobile`:
   - 캡션·엔진 패널·키 안내 숨김. 폰 베젤·다이내믹 아일랜드 모형·가짜 상태바(13:00, 배터리) 숨김. 앱 화면이 `100dvh`·`100vw` 전체를 쓴다. 안전 영역(`env(safe-area-inset-*)`) 반영.
   - 아일랜드 알림(`#island`)은 상단 고정 토스트로 유지(가로 폭 `calc(100vw - 24px)`).
   - 데스크톱 기준으로 고정 px로 짠 블록(폭 393px 기준 등)이 360~430px 폭에서 넘치지 않게. 가로 스크롤 0. 큰 숫자(만족도 79 : 83)는 `clamp()`로.
   - 하단 CTA 버튼은 `env(safe-area-inset-bottom)` 위에.
2. **터치로 끝까지** — 키보드가 없으니 각 단계 CTA로 1→5단계가 진행되는지 확인하고, 안 되는 곳(키로만 되는 동작: 저울 `,` `.`, `C` 조건 충돌, `H` 숨은 한 곳)은 화면 안 작은 버튼이나 탭 제스처로 대신한다. 저울 thumb은 터치 드래그(`pointer` 이벤트)로 움직이게.
   - 오른쪽 위 작은 원형 버튼 "엔진"을 누르면 엔진 패널을 바텀시트로 띄운다(LLM은 말만 바꾸고 숫자는 솔버가 만든다는 메시지가 투표자에게도 보이게). 닫기 가능.
   - 마지막 단계 끝에 "처음부터" 버튼.
3. **성능** — 모바일에서는 per-character blur 타이틀 애니메이션을 가볍게(blur 제거, 짧게). `prefers-reduced-motion` 존중은 유지.
4. **메타** — `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`, `theme-color` navy, OG 태그(`og:title` "TripFit", `og:description` "둘이 한 말로, 둘 다 OK인 일정", `og:image`는 `../docs/screens/02-plans.png`가 아니라 `og.png` 상대경로 — 파일은 총괄이 넣음).

## 규칙

- 디자인 문법(벤토 블록, 노치, 색, Inter Tight·Pretendard, 스프링) 유지. 새 색 금지.
- 데스크톱(≥1200px) 렌더 결과가 바뀌면 안 된다: 모든 모바일 스타일은 `body.mobile` 또는 미디어쿼리 안에만.
- `server/`, `solver/` 수정 금지(다른 작업이 동시에 고친다). 
- 완료 기준: `node --check`로 스크립트 문법 확인. Playwright(`../.venv/bin/python`에 없으면 시스템 python의 playwright, 없으면 생략하고 이유 기록)로 `file://.../web/index.html`을 390×844, 360×780 뷰포트에서 열어 단계별 스크린샷을 `codex/07_shots/`에 남기고 `document.documentElement.scrollWidth <= innerWidth` 확인. 1440×900 스크린샷도 1장.

## 마지막 메시지 형식

바뀐 부분 요약, 모바일에서 대체한 조작 목록, 스크린샷 경로, 가로 넘침 검사 결과, 확인 못 한 것.
