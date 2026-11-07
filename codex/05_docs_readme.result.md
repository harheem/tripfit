바뀐 파일: `README.md`, `PRD.md`, `SCREENS.md`. 코드는 수정하지 않았습니다.

README는 212줄이며 목차는 다음과 같습니다.

화면 → 30초 요약 → 심사 근거 → 실행법 → 데이터 흐름 → 점수 로직 → 실호출/샘플 → SKT·Vooy·MRT → 한계 → 저장소 구조 → 문서 → 출처·라이선스.

심사 항목 표 사본:

| 항목 | 근거 | 확인 방법 |
|---|---|---|
| 기술적 완성도 | 솔버 8개·서버 35개 통과, 1개 skip. 저장된 계산 시간 708/95/71ms | `solver/test_solver.py`, `server/test_api.py`, `server/test_mrt.py`, `web/demo_data.js` |
| 상업적 가능성 | 실제 체험 연결, 1인 35,000원. 전환율·매출 미검증 | `web/demo_data.js`, `solver/demo_builder.py` |
| 팀 실행력 | 엔진·API·화면·실상품·양보안 연결 | `server/app.py`, `web/index.html`, `codex/03_mrt_live.result.md`, `codex/04_whatif_concession.result.md` |
| 스폰서 리소스 활용 | OpenAI 파싱 연결, MRT 실상품 조회. SKT·Vooy는 통합 예정 | `server/parsing.py`, `scripts/fetch_mrt_snapshot.py`, `data/mrt_snapshot.json` |
| API 활용도 | JSON 검증·폴백, MRT 검색·상세·옵션, 실패 시 캐시 유지 | `server/parsing.py`, `solver/mrt_live.py`, `server/app.py` |
| 창의성·시도 | 체크리스트 저울·사람별 양보안·4곳 제외 계산 | `solver/tripfit_solver.py`, `solver/demo_builder.py` |
| 빌더 임팩트 | 키 없는 재생·CBC 계산, 개인 알고리즘의 앱 확장 | `web/index.html`, `web/demo_data.js`, `README_RUN.md` |

확인 결과: 금지 문구 0건, README 상대 링크 통과(스크린샷 예외), CAPS·PRD·SCREENS 대본 6문장 일치.

확인 못 한 것: 브라우저 렌더·자동재생, 외부 API 재호출, 정확한 집결지 좌표·소요시간. 공개 데모 URL과 스폰서 절은 요청대로 TODO로 남겼습니다. 스냅숏의 이전 좌표 설명 불일치도 문서에 명시했습니다.