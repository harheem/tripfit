# 12 — 줄표(—, –)와 가운데 점(·)을 모두 없애기

사용자 규칙: **AI 특유의 줄표와 가운데 점은 쓰지 않는다.** `tripfit/`의 사용자에게 보이는 글과 문서에서 `—`, `–`, `·`를 없앤다. 의미는 그대로 두고 자연스러운 한국어로 바꾼다.

## 대상

- 문서: `README.md`, `README_RUN.md`, `PRD.md`, `SCREENS.md`, `agentic-pay/README.md`
- 화면 문구: `web/index.html`, `web/pay/app.js`, `web/pay/index.html`, `solver/demo_builder.py`·`solver/demo_extras.py`·`server/*.py`가 만들어 화면에 나가는 문자열(라벨, 사유, 로그 문구), 그 뒤 `.venv/bin/python solver/export_demo.py`로 `web/demo_data.js` 재생성
- 제외: `vooy-mcp/`(다른 세션이 고침), `codex/`, 테스트 픽스처의 외부 원문, 코드 주석(보이지 않으면 그대로 둬도 됨)

## 바꾸는 법

- 나열 `A·B·C` → `A, B, C`. 짧은 라벨 안이면 `A와 B`.
- 화면 메타 줄 `전시 · 90분 · 도보 20분` → 구분 기호를 글자로 쓰지 말고 각 항목을 `<span>`으로 나눠 CSS `gap`/여백으로 띄우거나, 쉼표로. 디자인이 어색해지지 않게 기존 칩·알약 문법 활용.
- 상태 라벨 `LIVE · 실시간 계산` → `LIVE 실시간 계산`처럼 공백, 또는 두 요소로 분리.
- 줄표로 잇는 문장 `A — B` → 마침표로 나누거나 쉼표, 괄호.
- 숫자 범위 `13:00–18:30` → `13:00~18:30`.
- 테스트가 특정 문자열을 기대하면 테스트 기대값도 같이 고쳐라(로직 변경 금지).

## 완료 기준

`grep -rnE "·|—|–" README.md README_RUN.md PRD.md SCREENS.md agentic-pay/README.md web/index.html web/pay/app.js web/pay/index.html web/demo_data.js`가 0건(외부 상품명·원문 인용 등 불가피한 것만 예외로 목록 보고). `(cd solver && ../.venv/bin/python test_solver.py)`, `.venv/bin/python -m pytest server -q`, `(cd agentic-pay && node --test test/*.test.mjs)`, `node --check` 통과. 남긴 예외 목록과 바꾼 개수를 보고.
