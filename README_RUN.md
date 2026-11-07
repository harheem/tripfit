# TripFit 실행

상위 디렉터리에서 실행합니다. Python은 기존 `tripfit/.venv`를 사용합니다.

```bash
cd tripfit && .venv/bin/uvicorn server.app:app --port 8000
```

<http://localhost:8000/>에서 기존 프로토타입, `/docs`에서 API 명세를 확인할 수 있습니다.
시작 시 CBC 계산 1회로 워밍업하고 데모 캐시를 채웁니다. 모든 API 솔버 계산은 전역
`threading.Lock`으로 직렬화합니다. `--workers 1`(기본값)로 실행하세요.
캐시는 프로세스 메모리에만 존재하며 재시작하면 사라집니다.

## 테스트와 오프라인 데모 재생성

다음 명령은 `tripfit/` 기준입니다.

```bash
(cd solver && ../.venv/bin/python test_solver.py)
.venv/bin/python -m pytest server -q
(cd solver && ../.venv/bin/python export_demo.py)
```

API 테스트는 실제 CBC를 사용하고 외부 LLM 전송만 모의 처리합니다.
키가 없는 폴백, 제공자 순서·타임아웃, 스키마 재시도·고정 기본값, 입력 검증,
전체 항목 양보, 불가능 조건, 예약 시각 유지, 정적 파일, 캐시 갱신을 검사합니다.
`/api/demo`와 `web/demo_data.js`는 `live`·`computedAt`을 제외한 키가 같고,
`ms`·`solveMs`를 제외한 내용이 같아야 합니다.

기존 환경에는 필요한 패키지가 설치되어 있습니다. 재설치 시:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt`에 OpenAI 호환 클라이언트용 `openai`, 환경 파일 로딩용
`python-dotenv`, 테스트용 `pytest`를 명시했습니다. 새 패키지를 설치하지는 않았습니다.
Apple Silicon에서 CBC 로딩 오류가 나면 기존 PRD대로 `brew install gcc`가 필요합니다.

## 환경 변수

`python-dotenv`가 **`tripfit/../.env`**를 읽습니다. 이미 설정된 환경 변수를 덮어쓰지 않습니다.
키는 로그·응답·생성 파일에 기록하지 않습니다. `/api/health`는 키의 존재 여부만 반환하며,
키가 있어도 연결 성공이나 모델 설정 완료를 뜻하지는 않습니다.

| 변수 | 용도 |
|---|---|
| `OBA_API_KEY` | SKT A.X K2 인증 키 |
| `OBA_BASE_URL` | 제공받은 OpenAI 호환 API 주소(예: 서비스의 `/v1` 주소) |
| `OBA_MODEL` | 제공받은 A.X K2 모델 ID |
| `OPENAI_API_KEY` | 두 번째 제공자 인증 키 |
| `OPENAI_MODEL` | OpenAI 모델 ID. 없으면 OpenAI 단계 생략 |

A.X K2는 세 변수가 모두 있어야 호출합니다. OpenAI는 키와 모델이 모두 있어야 호출하며
공식 `https://api.openai.com/v1` 주소를 사용합니다. 임의의 모델 ID를 기본값으로 추측하지 않습니다.
순서는 **A.X K2 → OpenAI → 고정 데모 JSON**입니다. 각 제공자의 전체 시도(스키마 실패 시
재시도 1회 포함)는 최대 5초이며 SDK 자체 재시도는 끕니다. 네트워크/API 오류나 타임아웃은
다음 제공자로 넘어갑니다. 성공 시 실제 응답 모델명과 전체 파싱 소요 시간을 반환합니다.

LLM 출력은 `label`, `kind`, `intensity`, `quote`, 원문에 수량이 있을 때의 `full`만 받습니다.
서버가 PRD §6.3의 `match`, `zero`, 기본 `full`, 강도별 `weight`를 채웁니다.
원문에 없는 인용·수량, 지원하지 않는 종류, 임의 점수·추가 필드는 검증에 실패합니다.
현재 지원 항목은 전시, 골목, 소품샵, 카페에서 쉬기, 덜 걷기, 느긋하게입니다.
하드 조건은 서버 규칙으로 생성합니다(강한 전시 선호 → 전시 1곳, 카페 휴식 → 카페 1곳,
강한 도보 선호 → 도보 3,500m). 시각은 자정 기준 분입니다.

## 엔드포인트 예시

아래 응답에서 `…`는 긴 데이터의 생략입니다. `plan`은 기존 데모의 `id`, `label`, `stops`,
`walkM`, `walkMin`, `finish`, `sat`, `solveMs`, `checklist` 구조입니다.

| 요청 | 응답 예시 |
|---|---|
| `GET /api/health` | `{"ok":true,"solver":"CBC","llm":{"axk2":false,"openai":false}}` |
| `GET /api/demo?fresh=1` | `{"prefs":…, "series":[…], "defaultIdx":1, …, "live":true,"computedAt":"2026-11-07T03:00:00+00:00"}` |
| `POST /api/plan` `{"muted":[{"person":"서연","label":"덜 걷기"}],"tag_min":{}}` | `{"series":[…],"defaultIdx":…, "diffs":[…],"solveMs":…, "live":true}` |
| `POST /api/what-if` `{"pick":"mrt_leather_1600"}` | `{"plan":…, "diff":{"added":[…],"dropped":[…],…}}` |
| `POST /api/replan` `{"now_min":785,"exclude":["cafe_onion"],"keep":{"mrt_leather_1600":960}}` | `{"plan":…}` |
| `POST /api/parse` `{"messages":[{"name":"지민","text":"전시는 꼭 보고 싶어! 골목도 여기저기 구경하고 싶어"},{"name":"서연","text":"나 오늘 많이 못 걸어ㅠ 카페에서 좀 쉬고 싶어. 소품샵은 좋아"}]}` | `{"constraints":{"people":[…],…},"model":"demo-fixed","ms":…, "fallback":true}` (키가 없을 때) |

- `/api/demo`의 `computedAt`은 UTC ISO 8601 계산 완료 시각입니다. 캐시 조회로 바뀌지 않으며
  `?fresh=1`로 새로 계산해야 갱신됩니다. `live`는 데이터가 이 프로세스에서 계산되었다는 뜻입니다.
- `/api/plan`은 요청마다 계산합니다. 양보한 항목은 체크리스트에 남고 `weight: 0`, `muted: true`가
  붙습니다. 하드 제약은 유지됩니다. 한 사람의 모든 항목을 양보하면 그 사람 만족도는 0입니다.
  `tag_min: {"heritage": 1}`이면 숨은 후보 공씨책방을 포함해 풉니다.
- `/api/plan`에 `{"tag_min":{"heritage":5}}`를 주면 불가능한 요청이므로
  `{"infeasible":true,"relaxations":[{"label":"숨은 한 곳(서울미래유산) 5곳 조건 해제","changes":[{"kind":"tag_min","key":"heritage","from":5,"to":0}]}],…}`를 반환합니다.
  `what-if`·`replan`도 불가능하면 같은 진단 형태를 반환합니다. 엔진이 한두 조건 완화로도
  해를 찾지 못하면 `relaxations`는 빈 목록이고 `reason`에 실패 사유가 남습니다.
  도보 진단은 반올림 거리 대신 엔진이 실제 검사한 한도 해제(`to: null`)로 표현합니다.
- `/api/what-if`는 매번 기본 데모의 균형안을 기준으로 계산합니다. `1400`, `1600` 두 옵션을 지원합니다.
- `/api/replan`은 입력의 제외 장소와 예약 시각을 적용합니다. 이 MVP 요청에는 현재 좌표·완료 장소가
  없으므로 성수역에서 출발하고 완료 방문은 없는 것으로 계산합니다. `now_min`은 780~1110입니다.
- 입력 형식·알 수 없는 체크리스트/장소 ID는 HTTP 422를 반환합니다.

## 실제 호출과 남은 샘플

**실제 계산:** 데모 최초 조회/갱신, 일정 생성·양보·숨은 장소, 체험 추가, 여행 중 재계산은 모두
Python-MIP/CBC를 호출합니다. `tripfit_solver.py`의 수학은 변경하지 않았습니다.
API는 CBC로 고정하며 `TRIPFIT_SOLVER` 환경 변수로 다른 엔진을 선택하지 않습니다.
LLM은 환경 설정이 있을 때 실제 호출하고, 없거나 실패하면 `MESSAGES`와 `PREFS`에서 만든 고정 JSON입니다.
다른 문장을 입력했는데 폴백되면 `clarify`가 해당 결과가 샘플임을 알립니다.

**남은 샘플/범위:** 후보·좌표·영업시간·장소 점수·혼잡도는 `sample_seongsu.py`의 샘플,
도보는 직선 거리×1.3 추정, MRT 공방은 가상 상품입니다. 예약 가능 여부는 실조회하지 않습니다.
결제는 기존 화면의 목업이며 결제 API는 이번 범위에 없습니다.

**프론트 연결:** 첫 렌더 전에 HTTP(S) `/api/demo`를 최대 3초 확인해 라이브/재생을 선택합니다.
라이브 1단계는 `/api/parse`, 2단계 양보 토글은 `/api/plan`, 3단계 넣어보기는
`/api/what-if`, 5단계 다시 짜기는 `/api/replan`을 호출합니다. 넣어보기·재계산 실패 시
데모 결과로 재생하며 로그에 남깁니다. `file://`는 API를 호출하지 않고 기존 데이터를 재생하고,
양보 토글은 서버 연결 안내만 표시합니다. 숨은 한 곳·충돌 설명은 미리 계산된 결과를 사용합니다.
이번 `/api/plan` 입력은 `muted`·`tag_min`만 지원하며 기본 데모 두 사람의 조건으로 풉니다.
`/api/parse`의 임의 입력 결과를 일정에 연결하거나 세션을 유지하는 기능은 없습니다.

검증에서 실제 외부 LLM 인증·모델 지원 여부, TMAP/MRT/혼잡도 API, 브라우저의 실제 렌더·API 연동은 확인하지 않습니다.

01 작업 당시 검증 결과(프론트 연결 전): 솔버 테스트 **7 passed**, API 테스트 **22 passed (38.65s)**.
데모 재생성 후 기존 파일과 재귀 비교하여 `ms`·`solveMs` 외 모든 값이 일치했습니다.
솔버 엔진과 `web/index.html`은 파일 해시도 변경되지 않았습니다.
Uvicorn 시작·워밍업은 완료했으나, 작업 환경의 샌드박스가 포트 바인딩을
`Operation not permitted`로 차단해 실제 `localhost:8000` 접속은 확인하지 못했습니다.
TestClient에서는 `/`, `/demo_data.js` 및 API 응답을 확인했습니다.
