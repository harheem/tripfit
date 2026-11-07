구현 완료했습니다. **솔버 8개, 서버 62개 테스트 통과·1개 건너뜀**입니다. 실제 curl 검증은 샌드박스의 포트 바인딩 제한으로 완료하지 못했습니다.

**바뀐 파일**

- `server/app.py`: `/api/try`, 세션 기반 후속 계산, 호출 제한
- `server/parsing.py`: 규칙 파서, 조건 변환, 인용·unmatched 검증, LLM 동시성 2 제한
- `server/state.py`: 최대 100개·30분 LRU 세션과 토큰 버킷
- `solver/demo_builder.py`: 대안이 없을 때 진단 반환
- `server/test_try.py`, `server/conftest.py`: 테스트 추가·격리
- `README.md`: API 계약과 지원 범위 갱신

`web/`와 `solver/tripfit_solver.py`는 수정하지 않았습니다.

**요청·응답 예시**

`POST /api/try`:

```json
{"people":[
  {"name":"지민","text":"전시 꼭 보고 싶어"},
  {"name":"서연","text":"많이 못 걸어 카페에서 쉬고 싶어"}
]}
```

성공 시 `/api/demo` 데이터에 `sessionId`, `source`, `unmatched`가 추가됩니다. 조건이 없으면 `needsMore`, 불가능하면 `infeasible`과 `explanation`을 반환합니다.

**두 문장 쌍의 결과 — TestClient·실제 CBC**

| 입력 | 추출 조건 | 균형안 일정 | 만족도 지민/서연 |
|---|---|---|---|
| 위 요청 | 지민: 전시 / 서연: 덜 걷기·카페에서 쉬기 | 13:18 블루보틀 → 14:13 디뮤지엄 | 100% / 86% |
| “골목 산책 느긋하게, 소품샵은 꼭” / “걷는 건 괜찮아 전시 위주로” | 지민: 골목·느긋하게·소품샵 / 서연: 전시 | 13:02 소품샵 골목 → 13:39 대림창고 → 14:47 수제화거리 | 100% / 100% |

두 응답 모두 HTTP 200, `series` 1개, provider는 `rules`였습니다.

| 입력 | 파싱 | 전체 데모 계산 | 요청 전체 |
|---|---:|---:|---:|
| 첫 번째 | 1ms | 4,025ms | 4,038ms |
| 두 번째 | 0ms | 7,567ms | 7,615ms |

**확인 못 한 것**

8011 서버는 `operation not permitted`로 바인딩에 실패해 종료됐습니다. 실제 curl 응답, OpenAI 실호출, 브라우저 1~5단계 동작은 미확인입니다.

[상세 검증 기록](/Users/harheem/Library/Application%20Support/Claude/scratch-workspaces/8abcbd08-cf49-48d2-a8c8-1227fcb10a42/ea79a99b-4f99-4b96-bb73-f0adf342658a/scratch-2026-11-06-917dcc/tripfit/codex/06_try_backend.result.json)