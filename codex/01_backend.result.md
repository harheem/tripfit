구현 완료했습니다. 솔버 **7개**, API **22개 테스트 통과**. 데모 재생성 결과는 시간값을 제외하면 원본과 동일합니다.

변경·신규 파일:

- 신규: `solver/demo_builder.py`, `server/app.py`, `server/parsing.py`, `server/test_api.py`, `README_RUN.md`
- 수정: `solver/export_demo.py`, `solver/sample_seongsu.py`(import 호환), `requirements.txt`
- 재생성: `web/demo_data.js`
- `solver/tripfit_solver.py`, `web/index.html`은 변경하지 않았습니다.

엔드포인트 예시(`…`는 생략):

| 요청 | 응답 |
|---|---|
| `GET /api/health` | `{ok:true, solver:"CBC", llm:{axk2:false, openai:false}}` |
| `GET /api/demo?fresh=1` | `{series:[…], …, live:true, computedAt:"…"}` |
| `POST /api/plan` `{muted:[{person:"서연",label:"덜 걷기"}],tag_min:{}}` | `{series:[…],defaultIdx:…,diffs:[…],solveMs:…,live:true}` |
| `POST /api/what-if` `{pick:"mrt_leather_1600"}` | `{plan:…,diff:…}` |
| `POST /api/replan` `{now_min:785,exclude:["cafe_onion"],keep:{mrt_leather_1600:960}}` | `{plan:…}` |
| `POST /api/parse` `{messages:[{name:"지민",text:"전시는 꼭 보고 싶어"}]}` | `{constraints:…,model:"demo-fixed",ms:…,fallback:true}` — 키 없을 때 |
| `GET /` | 기존 프로토타입 HTML |

실행:

```bash
cd tripfit && .venv/bin/uvicorn server.app:app --port 8000
```

테스트·재생성(`tripfit/` 기준):

```bash
(cd solver && ../.venv/bin/python test_solver.py)   # 7 passed
.venv/bin/python -m pytest server -q               # 22 passed
(cd solver && ../.venv/bin/python export_demo.py)  # 재생성·원본 비교 통과
```

남은 샘플: 장소·혼잡도·가상 공방·추정 도보 거리·결제 목업. 프론트는 기존 재생 방식이며, 파싱 결과를 `/plan`에 연결하는 작업은 포함하지 않았습니다.

미확인: 외부 LLM 실제 인증·응답. Uvicorn 워밍업은 성공했지만 샌드박스가 포트 바인딩을 차단해 실제 localhost 접속은 확인하지 못했습니다. 정적 페이지와 API는 TestClient로 확인했습니다.