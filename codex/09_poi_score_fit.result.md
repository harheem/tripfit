기능을 반영했지만, **API 응답 한 줄과 실제 브라우저 검증이 남았습니다.**

바뀐 파일: `web/index.html`, `details.css`, `demo_data.js`, `logo.svg`, `favicon.svg`, `solver/demo_builder.py`, `demo_extras.py`, `server/test_demo_extras.py`, `codex/09_*` 검증·결과 파일입니다.

1. 큰 숫자와 단위를 함께 맞추는 `fitNumber()`를 적용하고 오도미터를 유지했습니다.
2. 강도 알약, 펼치는 가중평균 식, 낮은 만족도 표시와 로그를 추가했습니다.
3. 일정 카드·지도·합의 아이콘에서 Q 구성요소와 채운 말을 담은 POI 시트를 엽니다.
4. 로고·favicon과 0단계 진입 애니메이션을 추가했습니다.
5. MRT 버튼·가격·추정 표시·대비·시각 칩·시작 카드 폭을 개선했습니다.
6. max-min 추천, 결과 미리보기, 양보 장부·저장·초기화·다음 차례를 연결했습니다.

| 사람 | 계산식 | 계산 / sat | 일치 |
|---|---|---|---|
| 지민 | (100×1.0 + 50×0.7) ÷ 1.7 | 79.4 / 79.4 | 예 |
| 서연 | (65×1.0 + 100×0.7 + 75×0.7 + 100×0.7) ÷ 3.1 | 83.1 / 83.1 | 예 |

검증은 솔버 **8개 통과**, 서버 **75개 통과·2개 실패·1개 건너뜀**입니다. 두 실패는 `/api/what-if`의 `recommended` 누락입니다. 구문 검사와 DOM 전체 흐름은 통과했습니다.

스크린샷은 `codex/09_shots/`에 생성하려 했으나 Chromium 권한 오류로 **PNG를 만들지 못했습니다**. 실제 숫자 넘침·줄바꿈·브라우저 콘솔 검증도 미확인입니다.

[상세 결과](</Users/harheem/Library/Application Support/Claude/scratch-workspaces/8abcbd08-cf49-48d2-a8c8-1227fcb10a42/ea79a99b-4f99-4b96-bb73-f0adf342658a/scratch-2026-11-06-917dcc/tripfit/codex/09_poi_score_fit.result.md>)

요청하신 **`server/app.py` 수정 금지** 때문에 반환문은 그대로 두었습니다. 이 제한의 예외로 `recommended`를 응답에 포함하는 한 줄을 추가해도 될까요?