# 09 — 문구 정리: "양보" 없애기 + 줄표·가운데 점 없애기 (코드 동작 변경 없음)

너는 `vooy-mcp/` 폴더에서 일한다. **동작·계약·도구 이름·인자 키는 바꾸지 않는다. 사람에게 보이는 문구만** 바꾼다. 마감이 촉박하니 정확하고 빠르게.

## 규칙 1: "양보"라는 말을 쓰지 않는다 (사용자 결정). 단톡방에서 실제로 쓰는 말로

"양보"는 손해 보는 느낌이라 쓰지 않는다. 대신 **"이번엔 빼도 돼"(포기가 아니라 이번 코스에서만 뺌)**와 **"다음엔 ○○ 먼저"(뺀 사람이 다음에 먼저 고름)**로 말한다. 번역투나 명사형("다음으로 미룰 것", "우선권", "조건 해제")은 쓰지 말고, 친구끼리 단톡방에서 하는 말투로 쓴다.

| 자리 | 쓸 말 |
|---|---|
| 대본: 서연이 예산을 놓아줄 때 | "예산은 좀 넘어도 괜찮아" |
| 대본: 조건 충돌 뒤 지훈이 놓아줄 때 | "그럼 난 걷는 거 좀 해도 돼" |
| 사람 타일 위 작은 알약 | "다음엔 먼저" |
| 카드 헤드라인(누가 뺐을 때) | "서연 덕분에 다들 OK" |
| 카드·텍스트에서 뺀 항목 설명 | "이번엔 뺐어요: 2만원 안으로" |
| 다음 차례 안내 | "다음엔 서연이 먼저 골라요" |
| 불가능할 때 제목 | "이대로는 안 돼요. 하나만 빼면 돼요" |
| 불가능 선택지 한 줄 | "지훈의 '1km 이내'를 빼면 다들 100%" |
| 선택지 버튼 | "이걸로 할게" |
| 위젯이 대화에 남기는 메시지(ui/message) | "지훈은 걷는 거 이번엔 빼도 돼" |
| 되돌리기 | "되돌리기"(그대로) |
| 오류·안내의 "조건 해제" | "빼기" |

- 대상: `hapui/text.py`(content), `hapui/planner.py`·`hapui/schema.py`·`hapui/server.py`의 사람에게 보이는 문자열(오류 message·hint, concessions의 give_up 문구), `ui/board.html`, `ui/chat.html`(대본 포함), `README.md`, `RECIPE.md`, `ui/README.md`
- **도구 이름(`adjust_plan`), action `type: "yield"`, JSON 키는 그대로.** 문서에서 `yield`는 "이번엔 빼기(yield)"처럼 설명
- `ui/chat.html` 직접 입력 규칙: 사람 이름 + ("양보" 또는 "빼도" 또는 "넘어도" 또는 "괜찮아" 또는 "다음에")면 adjust_plan yield. 데모 안내 문구는 "'○○은 이번엔 빼도 돼'처럼 말해 보세요"
- RECIPE 지침: 사용자가 "양보할게", "빼도 돼", "넘어도 괜찮아", "다음에 해도 돼" 중 무엇이라고 해도 `adjust_plan(type=yield)`을 부르게. 결과를 전할 땐 "이번엔 뺐어요"와 "다음엔 ○○ 먼저"로
- 도구 description의 **검색용 예문**에는 사용자가 실제로 쓸 수 있는 "양보할게"를 남겨도 된다(받아들이는 쪽). 우리가 출력하는 문구에는 쓰지 않는다
- 문장이 어색하면 더 짧고 구어체로. 소리 내어 읽었을 때 친구가 단톡방에 쓸 법한 말인지가 기준

## 규칙 2: 줄표(—, –)와 가운데 점(·)을 쓰지 않는다 (사용자 규칙)

- 나열은 쉼표, 문장 연결은 마침표나 괄호, 숫자 범위는 물결표(13:00~18:00), 화면 메타 줄은 기호 대신 CSS `gap`의 별도 span
- 대상: 위 규칙 1의 모든 파일 + `IDEAS.md`·`PRD.md`는 **제외**(내부 기획 문서)
- 마크다운 표의 `|`, 코드 블록 안 JSON 키, URL은 건드리지 마라
- 확인: `grep -nE "·|—|–" README.md RECIPE.md ui/README.md ui/board.html ui/chat.html hapui/*.py` → 0건. `grep -n "양보" README.md RECIPE.md ui/board.html ui/chat.html hapui/text.py` → 0건(도구 description 예문은 server.py에 남을 수 있음, 그건 허용하고 결과 요약에 위치를 적어라)

## 규칙 3: README 예시는 실제 출력으로 다시

`text.py` 문구가 바뀌었으니 README "예시 대화"의 결과 텍스트는 **지금 코드로 다시 돌린 실제 출력**으로 바꿔라: `.venv/bin/python scripts/smoke_mcp.py --in-process`로 `scripts/smoke_result.json`을 다시 만들고 거기서 옮긴다(지어내지 말 것). README의 "검증 결과" 표 숫자(pytest 수)도 실제 값으로. 공개 서버 응답 시간 행은 손대지 마라(배포 뒤 이쪽에서 갱신).

README에 `/chat` 데모 링크 절을 맨 위 "바로 써 보기" 바로 아래 추가: "링크 하나로 보기: https://hapui.z2p0c2j9j5zsp.ap-northeast-2.cs.amazonlightsail.com/chat (vooy 연결 화면을 재현한 데모, 계산과 위젯은 공개 MCP 서버 실호출, 장소는 성수 샘플)". 스크린샷 자리는 `docs/chat_live_1.jpg`, `docs/chat_live_2.jpg`(파일은 이쪽에서 넣는다. 링크만).

## 확인

- `.venv/bin/python -m pytest -q` 통과(문구에 의존하는 테스트는 새 문구로)
- 위 grep 확인
- 보안 grep 0건: `grep -nE "innerHTML\s*=\s*[^'\"\`]|eval\(|new Function|on[a-z]+=\"" ui/board.html ui/chat.html`

## 끝에 남길 요약

바뀐 파일, 남긴 "양보"의 위치와 이유, pytest 수, README 예시의 출처
