# 03 — 가상 공방을 마이리얼트립 실상품으로 교체

너는 `tripfit/` 폴더에서 일한다. 지금 3단계 "체험 넣어보기"의 가죽공방 원데이클래스(`solver/sample_seongsu.py`의 `mrt_leather_1400/1600`)는 **가상 상품**이다. 심사 기준에 "스폰서 리소스 활용", "API 활용도"가 크게 들어가므로, 마이리얼트립 공개 MCP의 실상품·실시간 시작 시각으로 바꾼다. `PRD.md` §1.2, §6.5와 `README.md`를 먼저 읽어라.

## 마이리얼트립 MCP (인증 없음)

- `POST https://mcp-servers.myrealtrip.com/mcp`, JSON-RPC `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":..., "arguments":{...}}}`. 헤더 `Content-Type: application/json`, `Accept: application/json, text/event-stream`.
- `searchTnas {query}`: 결과가 위젯 JSON 텍스트(`result.content[0].text`)로 온다. 상품명, `⭐ 평점 (리뷰 수)`, 가격, `https://experiences.myrealtrip.com/products/<gid>` 링크가 들어 있다. 주의: "성수 공방" 검색의 첫 결과가 홋카이도 투어였다 → 검색어 여러 개를 시도하고 제목·상세에서 서울/성수 여부를 걸러야 한다.
- `getTnaDetail {gid, url}`: 설명 텍스트(집결지·소요시간이 텍스트 안에 있음).
- `getTnaOptions {gid, url, selectedDate}`: 날짜별 시작 시각·재고·가격. "automatic lookup is restricted" 류 응답이면 미확인.
- `tools/list`로 실제 인자 이름을 먼저 확인하라.

## 만들 것

1. **`solver/mrt_live.py`** — 위 세 도구의 클라이언트와 파서. `search_products(queries) -> [{gid, url, name, rating, reviews, price}]`, `get_detail`, `get_options(gid, url, date)`. 타임아웃 10초, 실패 시 예외 대신 `None`.
2. **`scripts/fetch_mrt_snapshot.py`** — 검색어 후보(예: "성수 원데이클래스", "성수 공방", "서울 성수 체험", "서울 가죽공방", "서울 원데이클래스")로 찾고, **성수동(또는 서울숲·뚝섬 인근)에서 하는 상품 1~2개**를 고른다(제목·상세 텍스트의 지명으로 판정, 근거를 남김). 날짜는 `MRT_DATE`(기본 `2026-11-14`, 토요일)로 시작 시각을 조회한다. 결과를 `data/mrt_snapshot.json`에 저장: `{fetchedAt, date, queriesTried, picked:[{gid,url,name,rating,reviews,price,durationMin,meetingText,lat,lng,coordSource,options:[{start:"HH:MM", available:true|false|null, price}]}], rejected:[{name, reason}]}`.
   - 좌표: 상세의 주소·장소명으로 성수 안 위치를 정한다. 확실하지 않으면 성수역 근처 근사 좌표 + `coordSource:"approx"`.
   - 소요시간: 상세에서 읽고, 없으면 120분 + `durationSource:"default"`.
   - 성수 상품이 하나도 없으면 가장 가까운 서울 상품을 고르고 그 사실을 `picked[].note`에 적는다. 그래도 없으면 스냅숏 없이 끝내고 기존 가상 상품을 유지(이유 출력).
3. **샘플 데이터 연결** — `solver/sample_seongsu.py`(또는 새 `solver/mrt_places.py`)가 `data/mrt_snapshot.json`이 있으면 시작 시각 옵션마다 `Place`를 만들고(같은 `group`, `fixed_start_min`, `price`, `source="mrt"`, `availability`, `url`), 없으면 기존 가상 공방을 쓴다. 장소 사실값(`PLACE_FACTS`)의 평판은 실제 평점·리뷰 수로 채운다. 체험 id는 `mrt_<gid>_<HHMM>` 형식.
   - `solver/demo_builder.py`·`export_demo.py`가 바뀐 id를 쓰게 고친다(what-if는 "가능한 시작 시각 중 균형안 기준으로 넣을 수 있는 것" 두 개, 재계산의 keep도 그 id). 하드코딩된 `mrt_leather_*` 참조를 모두 찾아 바꿔라(`server/`, `web/index.html` 포함).
4. **서버** — `GET /api/mrt` → 스냅숏 요약. `POST /api/mrt/refresh` → 실호출로 스냅숏 갱신(10초 타임아웃, 실패 시 기존 유지). 3단계 진입 시 프론트가 `/api/mrt`를 불러 엔진 로그에 `MyRealTrip searchTnas·getTnaOptions · 조회 HH:MM` 을 찍게 한다.
5. **화면** (`web/index.html`) — 체험 시트의 상품명·가격·평점(리뷰 수)·시작 시각·가용 여부를 스냅숏 값으로 보여 주고, "마이리얼트립에서 보기" 링크(새 탭)를 단다. 예시 상품 표기("예시 상품")는 실상품일 때 지운다. 좌표·소요시간이 추정이면 작은 "추정" 알약.
6. **테스트** — 네트워크 없이 도는 테스트는 스냅숏 픽스처로(`server/test_api.py`, `solver/test_solver.py`가 계속 통과). 실호출 테스트는 `RUN_NETWORK_TESTS=1`일 때만.
7. `export_demo.py`로 `web/demo_data.js`를 다시 만든다. 숫자가 바뀌면 바뀐 핵심 숫자(균형안 만족도, what-if에서 빠지는 곳·만족도 변화, 재계산 결과)를 마지막 메시지에 표로 남겨라(문서·피치 대본 갱신용).

## 규칙

- 네트워크는 마이리얼트립 MCP 호출에만 쓴다. 상품 설명문을 길게 복제해 저장소에 남기지 말고(집결지 한 줄 정도만), 이미지는 링크로만.
- `solver/tripfit_solver.py`의 수학은 바꾸지 마라.
- 완료 기준: 실제 스냅숏 파일 생성(실패하면 이유), `(cd solver && ../.venv/bin/python test_solver.py)`와 `.venv/bin/python -m pytest server -q` 통과, `node --check`로 `index.html` 스크립트 문법 확인.

## 마지막 메시지 형식

고른 상품(이름·gid·평점·리뷰·가격·시작 시각·가용 여부·좌표 근거), 버린 후보와 이유, 바뀐 파일, 바뀐 데모 숫자 표, 테스트 결과, 확인 못 한 것.
