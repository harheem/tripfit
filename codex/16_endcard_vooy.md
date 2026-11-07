# 16: 발표 마지막 장과 Vooy 단톡방 입구 (web/index.html만)

너는 `tripfit/` 폴더에서 일한다. 코드 프리즈가 17:00이라 **30분 안에 끝낼 작은 작업**이다. `web/index.html`만 고친다. 문구 규칙: 줄표(—, –)와 가운데 점(·) 금지, 이모지 금지, 짧은 존댓말. 디자인 문법(벤토 블록, 노치, 라임, Inter Tight 숫자) 유지.

## 1. 마지막 장(6단계 다음, "07 / 07")

발표를 맺고 피플스 초이스 투표로 이어 주는 화면. 5단계 끝 CTA("처음부터" 앞)에서 넘어가고, 키 `7`과 `→`로도 간다. 진행 막대·캡션 번호도 7칸으로.
- 앱 화면(폰 안): 큰 로고, 한 줄 소개 "여행 성향은 달라도 함께이고 싶은 두 사람을 위해, 둘 다 OK인 하루를 계산합니다", 아래 블록 세 개:
  - "직접 해 보기" 라임 블록: 공개 데모 QR(https://harheem.github.io/tripfit/) + 주소 텍스트
  - "단톡방에서 부르기" lilac 블록: vooy 단톡방 데모 QR(`VOOY_CHAT_URL`) + "vooy에서 @TripFit을 부르면 같은 엔진이 답해요"
  - "코드" navy 블록: GitHub QR(https://github.com/harheem/tripfit)
- 함께 쓴 것(작은 알약 줄): 마이리얼트립 MCP, SKT Agentic Pay, vooy MCP, Articul8 Bivia, OpenAI
- 데스크톱 왼쪽 캡션: 제목 "둘 다 OK인 하루", 설명 "같은 엔진이 앱, 단톡방, 결제를 함께 움직여요. 투표 부탁드려요."
- QR은 cdnjs의 `qrcodejs`(정확한 버전 고정, 예: qrcodejs 1.0.0)로 그리거나, 외부 라이브러리 없이 SVG로 생성. 로드 실패 시 주소 텍스트만.

## 2. Vooy 입구

`const VOOY_CHAT_URL = "https://hapui.z2p0c2j9j5zsp.ap-northeast-2.cs.amazonlightsail.com/chat";`
- 데스크톱 엔진 패널 아래(또는 키 안내 위) 작은 lilac 알약 링크 "vooy 단톡방에서 보기 ↗" 대신 화살표 svg 아이콘 사용, 새 탭.
- 0단계 "우리 대화로 바꿔 보기" 버튼 아래 작은 텍스트 링크 "단톡방에서 부르는 모습 보기(vooy)".
- 휴대폰 모드에서도 보이게.

## 완료 기준

`node --check`(스크립트 추출) 통과, 기존 자동재생 `A`가 5단계에서 멈추던 흐름은 그대로(마지막 장은 자동재생에 포함해도 됨). 변경 부분에 금지 기호 0건. 결과 메시지에 바뀐 점.
