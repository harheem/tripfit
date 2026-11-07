완료했습니다.

- **README**: 요청한 순서로 작성했습니다. 예시 결과 3개는 로컬 MCP smoke가 받은 실제 `content`와 일치합니다.
- **식당 중복**: 식당 수 상한이 없어 생기던 문제였습니다. 기본 최대 1곳, 명시적으로 여러 곳을 원할 때만 한도를 늘렸습니다. 근사해에도 적용됩니다.
- **양보 후 0%**: 기존 smoke는 카페 휴식 조건이 남아 미충족된 것이므로 정상적인 0%였습니다. 계산할 조건이 모두 사라진 경우는 `pct: null`·“조건 없음”으로 표시하고 최소 만족도에서 제외했습니다.
- **보드**: 아일랜드 최대 폭을 화면−32px로 제한하고 긴 문구를 두 줄로 처리했습니다. 첫 등장 애니메이션은 최대 660ms이며 reduced motion을 유지했습니다.

변경 파일: `README.md`, `hapui/{mapping,planner,schema,text}.py`, `hapui/engine/tripfit_solver.py`, `ui/{board.html,README.md}`, `tests/test_planner.py`, `scripts/{smoke_mcp.py,smoke_result.json}`.

검증: **pytest 54개 통과**, MCP smoke 9회 통과, `/healthz` 200, 지정 grep **0건**, JavaScript 구문 검사 통과.

미확인: 실제 375px 브라우저 렌더링, vooy 연결·MCP Apps 표시, 수정본 원격 배포. `docs/board.png`는 파일 없이 이미지 링크만 두었습니다.