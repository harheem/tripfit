# 04 — 실상품을 "못 넣는다 → 무엇을 양보하면 넣을 수 있다"로 보여 주기

너는 `tripfit/` 폴더에서 일한다. 03 작업으로 마이리얼트립 실상품(서울숲 힐링 숲체험, gid 3828508, 집결지 서울숲 방문자센터)이 들어왔다. 총괄 리뷰에서 좌표를 실제 집결지 근처(`37.5437, 127.0397`, `data/mrt_snapshot.json`, `scripts/fetch_mrt_snapshot.py`의 ANCHORS)로 바로잡았더니, 시간창 13:00–18:30에서 들어갈 수 있는 시작 시각은 15:00 하나이고, 균형안에 넣으면 **불가능**하다. diagnose 결과 최소 양보안은 "숲체험 필수 해제", "전시 최소 1곳 조건 해제", "카페 최소 1곳 조건 해제"다. 지금 `web/demo_data.js`의 `whatif.pick`이 null이고 replan도 null이라 3~5단계가 깨진다.

이 결과를 숨기지 말고 **데모의 핵심 장면으로** 바꾼다: "숲체험을 넣으면? 지금 조건으로는 안 돼요. 서연의 '카페 1곳'(또는 지민의 '전시 1곳')을 양보하면 넣을 수 있어요." 사람의 하드 조건을 양보하는 건 2단계의 "이 말은 양보할게"(소프트 항목)와 같은 문법이다.

## 할 일

1. **양보안 구조화** (`solver/demo_builder.py`, 필요하면 `server/`의 래퍼에서; `solver/tripfit_solver.py`의 수학은 바꾸지 말 것)
   - what-if가 불가능하면 `{infeasible: true, relaxations: [{id, label, owner: "서연"|"지민"|null, kind: "category_min"|"must"|"walk"|"deadline", changes: [...]}]}`로 돌려준다. owner는 그 하드 조건을 말한 사람(카페 → 서연, 전시 → 지민, 도보 한도 → 서연; Constraint 출처는 `export_demo.MESSAGES`의 hard marks).
   - "체험 자체를 빼기"(필수 해제)는 선택지에서 제외한다(넣으려는 게 목적이므로).
   - 양보안 하나를 적용해 다시 푼 결과(`plan`, `diff`)를 함께 계산한다. 데모 기본 선택은 서연의 "카페 최소 1곳" 해제(없으면 첫 번째 양보안).
   - `demo_data.js`의 `whatif`: `{pick, infeasible, relaxations, chosen: {relaxationId, plan, diff}}`. 넣을 수 있는 경우(가상 상품 폴백 등)는 기존 모양을 유지(`infeasible: false`).
2. **API** — `POST /api/what-if {pick, relax?: relaxationId}`: relax 없이 부르면 가능하면 plan, 불가능하면 양보안 목록. relax를 주면 그 양보를 적용한 plan·diff.
3. **화면** (`web/index.html`, 3단계)
   - 시간 시트에서 15:00을 고르고 [넣고 다시 계산] → 아일랜드 "지금 조건으론 못 넣어요" → 제목 "숲체험을 넣으려면\n하나를 양보해야 해요" → 양보안 블록들(사람 색 점 + "서연의 '카페 1곳'을 양보", "지민의 '전시 1곳'을 양보", 기타)을 버튼으로 보여 준다.
   - 버튼을 누르면(라이브: `/api/what-if` relax, 재생: `whatif.chosen`) 일정이 바뀌는 기존 애니메이션(빠지는 곳 트레이, 차이 숫자, 해칭된 체험 블록 스크롤)을 그대로 쓴다. `v._run`(자동재생)은 15:00 선택 → 서연 카페 양보 선택까지 진행.
   - 체험 카드·시트·영수증·4단계 결제 항목·5단계 문구에서 "공방", "16:00" 하드코딩을 모두 없애고 상품명(짧은 별칭: 예 "서울숲 숲체험")과 실제 시작 시각을 쓴다. 가격 35,000원 × 2.
4. **4·5단계 연결** — 4단계 합의는 `whatif.chosen.plan`(라이브면 방금 받은 plan)을 쓴다. 5단계 재계산은 그 plan의 첫 번째 비고정 장소를 "지금 붐빔(샘플)"으로 두고(카페가 있으면 카페 우선), 체험 시작 시각을 lock한 채 `reoptimize`로 다시 푼다. `demo_builder.py`의 "어니언" 하드코딩·assert를 없애고 이 규칙으로 정한다. `replan`이 null이 되면 안 된다(실패하면 다음 비고정 장소로 시도).
5. **캡션 대본** (`web/index.html`의 `CAPS[3]`, `CAPS[5]`) — 3: "숲체험을 넣으면? 지금 조건으론 안 된다고, 대신 누가 무엇을 양보하면 되는지 바로 계산해요." 5: "가서 붐비면, 예약한 숲체험은 지키고 나머지만 다시 짜요. 말에서 실행까지, TripFit입니다."
6. `export_demo.py`로 `web/demo_data.js` 재생성. 테스트 추가: what-if 불가능 시 양보안에 owner가 있고 필수 해제가 없음, chosen.plan이 체험을 포함하고 하드 조건(남은 것)을 지킴, replan이 null이 아니고 체험 시각이 유지됨.

## 규칙

- 솔버 수학 변경 금지. 키·비밀값 금지. 디자인 문법 유지(블록·색·스프링).
- 완료 기준: `(cd solver && ../.venv/bin/python test_solver.py)`, `.venv/bin/python -m pytest server -q` 통과, `node --check`로 스크립트 문법 확인, `web/demo_data.js`에서 `whatif.chosen.plan`과 `replan.plan`이 null이 아님.

## 마지막 메시지 형식

바뀐 파일, 새 데모 숫자 표(균형안, 양보안 목록, 선택한 양보 후 일정·만족도·빠진 곳, 재계산 결과), 테스트 결과, 확인 못 한 것.
