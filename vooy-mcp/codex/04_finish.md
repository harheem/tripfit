# 04 — TripFit for vooy 마무리: README, 품질 수정 2건, 보드 수정 2건

너는 `vooy-mcp/` 폴더에서 일한다. 서버(`hapui/`)와 보드(`ui/board.html`)는 이미 있고 테스트 51개가 통과한다. 이번에는 **제출용 마무리**다. 먼저 `PRD.md`(§3, §4, §6, §9.1)와 `codex/01_server.result.md`, `ui/README.md`를 읽어라.

## 배경 (바뀐 결정)

- 이 서버는 별도 프로젝트가 아니라 **"TripFit for vooy" — TripFit의 합의 엔진을 vooy 메신저 도구로 연 MCP 서버**다. 제출 저장소는 https://github.com/harheem/tripfit 하나이고, 이 폴더는 나중에 그 저장소의 `vooy-mcp/` 하위 폴더로 옮겨진다. 그래서 모든 경로는 이 폴더 안에서 끝나야 한다(상위 폴더 참조 금지, 단 `.env`는 선택).
- 배포됨: **https://hapui.z2p0c2j9j5zsp.ap-northeast-2.cs.amazonlightsail.com/mcp** (AWS Lightsail 서울, Streamable HTTP, 인증 없음). 헬스체크 `/healthz`.
- 스폰서는 README와 링크만 보고 판단한다. **README만 읽고 vooy에 붙여 써 볼 수 있어야 한다.**
- Linux에서는 `mip==1.15.0`, macOS에서는 `mip==1.16rc0`(requirements.txt 환경 마커). 1.16rc0의 Linux CBC는 SIGSEGV가 났다(2026-11-07 확인). 이 사실을 README에 적어라.

## 1. `README.md` (한국어, 이 순서)

1. 첫 줄: `# TripFit for vooy` 다음 줄에 "TripFit의 합의 엔진을 vooy 메신저 도구로 연 MCP 서버"
2. 한 문단 소개: 단톡방에서 각자 한 줄씩 말하면 다들 OK인 나들이 코스 3안과 누가 얼마나 양보하는지를 계산. "LLM은 숫자를 만들지 않는다 — 말을 조건으로 바꾸는 건 vooy, 숫자는 솔버와 공개 기본값표"
3. **바로 써 보기**: 서버 URL(위 주소), vooy 연결 방법("vooy 서비스 연결(사용자 지정 MCP) 화면에 URL 붙여넣기 → 도구 4개가 보이면 연결 완료", 전송 방식 Streamable HTTP, 인증 없음), 연결 뒤 말해 볼 예시 문장 3개
4. **예시 대화**: 3인(민지·지훈·서연) 성수 13:00–18:00. 사용자 말 → 불리는 도구와 인자(JSON 요약) → 돌아온 텍스트. 텍스트는 `scripts/smoke_result.json`이 있으면 거기서, 없으면 로컬에서 smoke를 돌려 **실제 출력**을 붙여라(지어내지 말 것). 양보 1회, 불가능 1회 포함
5. **스크린샷**: `docs/board.png`(보드 웹 화면, 폰 폭). 스크린샷은 이 세션 밖에서 넣을 수 있으니 자리만 만들고 파일이 없으면 "추가 예정"이라고 쓰지 말고 이미지 링크만 둔다
6. **도구 4개**: 이름, 언제 부르는지, 입력 예시 JSON, 출력 요약(content 텍스트 + structuredContent 주요 필드). `hapui/server.py`의 실제 스키마와 맞출 것
7. **무엇이 실제고 무엇이 샘플인가** 표: 솔버 계산(실제), 성수 장소(샘플, 식당 4곳 포함 이름에 "(샘플)"), 마이리얼트립 체험(실호출, 실패 시 표기), 도보(직선거리×1.3 추정), vooy가 넘긴 후보(vooy 데이터)
8. **공개 기본값표**: `hapui/mapping.py`의 `PUBLIC_DEFAULTS`를 표로
9. **견고성·보안**: PRD §5·§6 요약 + 실제로 넣은 환경 변수(`HAPUI_TOKEN`, `HAPUI_PUBLIC_HOST`, `HAPUI_PUBLIC_URL`, `HAPUI_TRUST_PROXY`, `HAPUI_RATE_PER_MIN`, `HAPUI_SOLVER_PER_MIN`, `HAPUI_HOST`)
10. **MCP Apps 위젯**: 도구가 `ui://hapui/board.html`을 내고, MCP Apps를 그리는 호스트에서는 대화 안에 보드가 뜬다. vooy가 그리는지는 미확인 → 결과 텍스트의 보드 링크(`/b/<token>`, 6시간 유효)로 같은 화면
11. **로컬 실행·테스트**: venv, `python -m hapui.server --port 8770`, `pytest`, `scripts/smoke_mcp.py <url>`, Docker 빌드(`--platform linux/amd64`)
12. **배포(Lightsail)**: 사용한 명령 순서(서비스 생성, `push-container-image`, 배포 JSON 예시 — 환경 변수 포함), 그리고 **행사 후 정리**: `aws lightsail delete-container-service --service-name hapui --region ap-northeast-2` (월 과금 방지)
13. **출처·라이선스**: 솔버는 TripFit `solver/tripfit_solver.py`를 복사해 `hapui/engine/`에 두고 예산·식사시간 제약 2개만 추가. 마이리얼트립 공개 MCP. 서울미래유산(공공누리 1유형) 문구가 있으면 표기

## 2. 품질 수정 (hapui)

- **연속 식사 금지**: 지금 균형안이 "국밥집 → … → 백반집"처럼 식당을 2곳 넣는다. 식당은 최대 1곳(누군가 `visit`로 식당을 2곳 이상 원했을 때만 그 수만큼). 솔버 원본 수학은 건드리지 말고 기존 `category_max`가 없으면 `hapui/engine/tripfit_solver.py`에 최소 제약 하나로 추가하되 출처 주석 아래에 "Hapui 추가"로 표시. 테스트 추가
- **양보 뒤 0%**: smoke의 "서연 예산 양보" 결과에서 "민지 우선" 안의 서연이 0%다. 원인을 찾아라. 양보한 항목만 남은 사람이면 0%가 아니라 "조건 없음"으로 표시하거나 계산에서 빼는 게 맞다. 고치고 테스트 추가

## 3. 보드 수정 (ui/board.html)

- 아일랜드 문구가 375px 폭에서 알약 밖으로 넘친다 → 알약 최대 폭 = 화면 폭 − 32px, 넘치면 두 줄 또는 말줄임
- 첫 등장 애니메이션 전체가 2초 넘게 걸린다 → 마지막 블록까지 700ms 안에 끝나게(순차 간격·지속 시간 조정). `prefers-reduced-motion` 동작 유지

## 규칙

- Python `vooy-mcp/.venv/bin/python`. 새 패키지 금지.
- 건드리지 마라: `PRD.md`, `IDEAS.md`, `Dockerfile`, `.dockerignore`, 상위 폴더 전부, `.env`.
- `hapui/server.py`의 보안·배포 관련 코드(Guard, `HAPUI_*` 환경 변수)는 동작을 바꾸지 마라.
- 완료 확인: `.venv/bin/python -m pytest -q` 통과, `grep -nE "innerHTML\s*=\s*[^'\"\`]|eval\(|new Function" ui/board.html` 0건.

## 끝에 남길 요약

바뀐 파일, 두 품질 버그의 원인과 수정, 테스트 수, README에 넣은 실제 출력의 출처, 확인 못 한 것.
