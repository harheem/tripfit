완료했습니다. 도구 이름, action 값, JSON 키와 계산 로직은 유지했습니다.

- 변경: `hapui/{text,planner,schema,server,mapping}.py`, `ui/{board,chat}.html`, README 2개, `RECIPE.md`, `scripts/smoke_result.json`
- “양보” 원문은 `hapui/server.py:121`의 검색용 입력 예문에만 남겼습니다. 기존 입력 인식은 Unicode 이스케이프로 유지했습니다.
- pytest **60개 통과**, MCP 스모크 **9회 통과**. 지정 금지 문자와 보안 grep **0건**입니다.
- README 예시는 `--in-process`로 재생성한 `smoke_result.json` 첫 세 호출의 실제 `content`를 그대로 옮겼습니다.
- `/chat` 링크와 스크린샷 링크 2개를 추가했습니다. 공개 서버 응답 시간 수치는 유지했습니다.