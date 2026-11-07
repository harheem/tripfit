# 15: Articul8 Bivia가 결제 직전 마지막 판단을 내리고, 거절 장면을 드라마틱하게

너는 `tripfit/` 폴더에서 일한다. 스폰서 Articul8의 디시전 모델 **Bivia**를 SKT 같이 결제의 "에이전트가 결제해도 되는가" 마지막 판단에 붙인다. 사용자 요청: **거절이 나오는 경우를 데모에서 드라마틱하게 보여 줄 것.** 먼저 `web/pay/app.js`, `web/pay/styles.css`, `web/pay/engine/*.js`, `server/pay_router.py`, `server/parsing.py`(레이트 리밋, 키 로드), `web/index.html`의 결제 결과 수신 부분, `agentic-pay/README.md`를 읽어라.

**문구 규칙: 줄표(—, –)와 가운데 점(·) 금지, 이모지 금지. 말투는 TripFit과 같은 짧은 존댓말.** 디자인 문법(TripFit 토큰, 확인서 한 장, 라임, red 블록) 유지.

## Bivia API (빌더 가이드에서 확인한 사실)

- `POST https://api.articul8.ai/bivia/choice`, 헤더 `Authorization: Bearer <A8_API_KEY>`, `Content-Type: application/json`
- 요청: `{"state": "<상황 설명 텍스트>", "question": "<질문>", "choices": ["...","..."], "mode": "fast", "allow_abstain": true}`
- 응답: `type`, `value`(고른 선택지 또는 abstain이면 null), `probability`, `distribution`(선택지별 확률), `status`("answered" | "abstained"), abstain이면 이유 필드, `model`(예: dec-1). 응답 필드 이름이 다르면 방어적으로 파싱.
- 키는 상위 폴더 `.env`의 `A8_API_KEY`(없으면 `BIVIA_API_KEY`). 코드, 로그, 결과에 키를 쓰지 마라.

## 1. 서버 `POST /api/pay/decide`

- 입력: 결제 직전 상황 `{item, people, lines:[{person, mandate_max, amount}], checks:[{key, ok, detail}], changed:{from,to}|null, merchant:{expected, actual}}`.
- 서버가 `state` 텍스트를 만든다(예: "두 사람이 마이리얼트립 서울숲 힐링 숲체험 15:00에 각자 1인 35,000원까지 결제를 맡겼다. 방금 다시 조회한 가격은 38,000원이다. 판매처는 마이리얼트립으로 맡긴 곳과 같다. 위임 기한은 16:50까지 남아 있다..."), `question`은 "에이전트가 지금 이 결제를 진행해도 되는가?", `choices`는 `["결제 진행", "결제 멈추고 다시 묻기"]`.
- Bivia 호출(타임아웃 8초, 기존 IP 레이트 리밋 공유). 응답 `{provider:"articul8-bivia", model, value, probability, distribution, status, reason, ms}`.
- 키가 없거나 실패하면 `{provider:"rules", value: 엔진 검사 결과로 정한 값, status:"answered", reason}` 반환. **rules일 때 distribution이나 probability를 지어내지 마라.**
- 안전장치: 엔진 검사 중 하나라도 실패했는데 Bivia가 "결제 진행"이라고 해도 결제는 막는다(최종 결정 = 엔진 검사 AND Bivia). 이 규칙을 응답 `final`과 `override_reason`으로 표시.
- 테스트(네트워크 없이, 모킹): 키 없음 → rules, Bivia answered/abstained 파싱, 엔진 실패 시 진행 응답이어도 final=stop.

## 2. 결제 화면(4단계) "마지막 판단" 블록

확인서 아래, 결제 버튼 위.
- 진입 시 `/api/pay/decide` 호출. 호출 중: navy 블록에 "Articul8 Bivia가 마지막으로 판단하는 중" + 작게 펄스.
- **통과**: 라임 테두리 블록 "결제해도 돼요", 확률(예: 97%), 선택지별 막대 두 줄(distribution), 출처 알약 `Articul8 Bivia dec-1, 180ms`. 결제 버튼 활성.
- **거절(드라마틱하게)**: 화면이 한 번 살짝 흔들리고(transform shake 300ms, reduced-motion이면 생략), red 블록이 아래에서 스프링으로 올라오며 큰 글씨 **"결제를 막았어요"**, 그 위에 비스듬한 도장 "STOP"이 찍히는 애니메이션(scale 1.4 → 1, 회전 -8deg). 아래에 이유 한 줄("방금 조회한 가격 38,000원이 두 분이 맡긴 35,000원을 넘었어요"), 확률 막대(결제 멈추고 다시 묻기 93%가 차오르는 애니메이션), 출처 알약. 결제 버튼은 잠기고 회색, 그 아래 "새 한도로 다시 맡기기" 버튼. 확인서의 해당 줄도 red X.
- **판단 보류(abstained)**: butter 블록 "확신이 없어서 결정하지 않았어요" + 이유, 결제 잠금, "사람이 직접 확인하기".
- rules일 때는 같은 블록 문법이되 출처 알약 `규칙 판단`(키 없음), 확률 막대 없음.
- "가격이 오르면?", "다른 곳에서 결제하려 하면?" 시뮬레이션 버튼을 누르면 이 판단을 다시 불러 거절 장면이 나온다. 다른 판매처 시나리오의 state에는 "결제 요청이 맡긴 곳이 아닌 다른 판매처에서 왔다"를 넣는다.
- 거절 시 부모(TripFit)에 기존 `status:"stopped"` 메시지로 `reason`과 `decider:"Articul8 Bivia"`를 보내고, TripFit 4단계 빨간 줄에 "Articul8 Bivia가 결제를 막았어요: 이유"로 표시. 엔진 로그 `ARTICUL8 Bivia 판단: 결제 멈춤 93%, 180ms`.

## 3. 문서

`agentic-pay/README.md`, `README.md`(SKT 절과 심사 근거 표의 스폰서 리소스 활용 행)에 Articul8 Bivia 사용(엔드포인트, 판단 질문, 최종 결정 = 엔진 검사 AND Bivia, 키 없을 때 규칙 판단)을 짧게 추가.

## 완료 기준

`(cd agentic-pay && node --test test/*.test.mjs)`, `.venv/bin/python -m pytest server -q`, `node --check` 통과. 바꾼 파일에서 금지 기호 0건. 결과에 바뀐 파일, 거절 장면 동작, 확인 못 한 것.
