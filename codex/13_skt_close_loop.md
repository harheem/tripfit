# 13 — SKT 트랙 보완: 결과 반환, 에이전트가 멈추는 장면, LLM이 쓰는 판매자 문의

너는 `tripfit/` 폴더에서 일한다. SKT 과제(전달받은 문구): 세 단계 **알려준다 → 대신한다 → (사람 승인 후) 끝까지 해낸다**. 핵심 문제는 "에이전트에게 내 카드를 맡기기 어렵다 → 맡길 수 있게 만드는 장치". 필수 흐름은 **일상 맥락 → 데이터 조회 → 선택과 확인 → 실행과 결제 → 결과 반환**. UX 방향은 "실제 영수증처럼, 착오 없이, 쉽게 믿고 승인". 지금 결과물(`web/pay/`, `server/pay_router.py`, TripFit 4단계 시트 `web/index.html`)에서 세 가지가 빠졌다. 먼저 `agentic-pay/README.md`, `web/pay/app.js`, `web/pay/engine/*.js`, `server/pay_router.py`, `server/parsing.py`(LLM 제공자 순서 A.X K2 → OpenAI, 키는 상위 `.env`), `web/index.html`의 결제 시트 부분을 읽어라.

**문구 규칙(사용자 지시): 줄표(—, –)와 가운데 점(·)을 절대 쓰지 마라.** 나열은 쉼표, 범위는 물결표, 화면 구분은 간격. 기존 디자인 문법(TripFit 토큰, 블록, 라임, 확인서 한 장 스타일) 유지. 이모지 금지.

## 1. 결과 반환 (가장 중요)

- `web/pay/`: 결제가 끝나면(영수증 단계 진입 시 1회) `window.parent.postMessage({type:"tripfit-pay", status:"paid", total, lines:[{person, amount, approval_no}], hash8, item:{gid, start, short_name}, at}, location.origin)`. 에이전트가 멈췄을 때(가격 인상, 예약 불가, 판매처 거절, 위임 취소)도 `status:"stopped", reason`으로 보낸다. 단독 실행(부모 없음)이면 아무것도 안 함.
- `web/index.html`: 메시지를 받으면(출처 확인) ① 결제 시트 닫힘 후 4단계 결제 블록이 "결제 완료" 상태로 바뀜: 사람별 금액과 승인번호, 기록 해시 앞 8자, "마이리얼트립에서 예약 확정" 알약 ② 일정 카드(4·5단계)의 해당 체험에 "결제 완료" 알약 ③ 아일랜드 "같이 결제 완료, 70,000원" ④ 엔진 로그 `AGENTIC PAY 결제 완료 70,000원, 승인 2건, 기록 d3ed107e`. stopped면 4단계에 빨간 한 줄(사유와 "다시 맡기기"). 이 상태는 5단계 재계산에도 유지(예약 시각 고정과 일관). 자동재생(`A`)은 결제 시트를 열지 않으므로 영향 없게.

## 2. 에이전트가 멈추는 장면을 겉으로, 위임 취소

- 4단계(이대로 승인해도 되는 이유) 결제 버튼 아래, 그리고 영수증 단계에 작은 테두리 알약 버튼 두 개를 **보이게**: "가격이 오르면?"(기존 가격 인상 시나리오), "다른 곳에서 결제하려 하면?"(기존 판매처 불일치 시나리오). 누르면 "시뮬레이션" 표시와 함께 기존 엔진 흐름을 실행하고, 에이전트가 멈추는 모습(확인서 해당 줄 red X, 결제 버튼 잠금, 다시 맡기기)을 그대로 보여 준다. "기술 정보" 토글의 테스트 버튼은 남겨도 됨.
- **맡긴 결제 취소하기(위임 철회)**: 2~4단계에서 사람별 위임 블록에 "맡긴 것 취소" 작은 버튼. 엔진에 `revokeMandate(world, mandate_id, by)`를 최소 추가(상태 REVOKED, 감사 로그 기록, 이후 결제 권한 발급·결제 시 거절 `MANDATE_REVOKED`). 확인서 "위임" 줄이 red X가 되고 결제 잠금, "다시 맡기기"로 복구 가능. 엔진 테스트에 철회 케이스 추가(기존 25개는 그대로 통과).

## 3. "대신한다": 판매자 문의를 LLM이 실제로 작성

- 서버 `POST /api/pay/inquiry {item:{short_name, start, date, meeting?}, people:[names], split:[amounts], question_hints?}` → `server/parsing.py`의 제공자 순서(A.X K2 키가 있으면 A.X K2, 없으면 OpenAI `OPENAI_MODEL`)로 판매자에게 보낼 짧은 문의(3~4문장, 존댓말, 2명, 15:00, 분담 결제 예정, 우천 진행 여부, 집결지 확인)를 생성. 응답 `{text, provider, model, ms}`. 실패하면 지금의 고정 문안 + `provider:"template"`. 타임아웃 12초, 기존 IP 레이트 리밋 공유. 입력은 데이터로만 취급(프롬프트 주입 방어 문구), 출력에 줄표와 가운데 점이 있으면 서버에서 쉼표로 치환.
- `web/pay/` 3단계 "판매자 문의 초안" 카드: 열릴 때(또는 3단계 진입 시) 위 API를 부르고, 작성 중 표시 후 텍스트와 작은 알약(`A.X K2 작성` / `OpenAI gpt-6.1-sol 작성` / `고정 문안`, ms)과 "보내지 않음" 표시. 정적 공개 링크(GitHub Pages, API 없음)에서는 고정 문안으로.
- 테스트(`server/test_pay_router.py`에 추가, 네트워크 없이): 제공자 없음 → template, 제공자 모킹 → provider·model·text 반환, 기호 치환.

## 4. 문서

`agentic-pay/README.md`와 `README.md`의 SKT 절에 SKT 필수 흐름 다섯 단계와 세 단계를 각각 무엇이 구현하는지 표로(결과 반환, 멈춤, 철회, LLM 문의 포함). 실제 테스트 수로 갱신.

## 규칙과 완료 기준

- 결제는 여전히 모의. 실제 전송 없음. 키를 코드·로그·결과에 쓰지 마라.
- `(cd agentic-pay && node --test test/*.test.mjs)`(기존 25 + 추가), `.venv/bin/python -m pytest server -q`, `(cd solver && ../.venv/bin/python test_solver.py)`, `node --check` 통과. `grep -nE "·|—|–"`가 바꾼 파일에서 0건.
- 결과 메시지: 바뀐 파일, 세 기능 동작 설명, 테스트 수, 확인 못 한 것.
