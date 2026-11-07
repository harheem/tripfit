# 10 — 같이 결제 화면 검증 및 스크린샷 인계

## 현재 상태

PNG **미생성**. Playwright 모듈과 Chromium은 설치되어 있지만, 이 작업 환경에서 Chromium이 실행 직후 아래 오류로 종료된다.

```
FATAL:base/apple/mach_port_rendezvous_mac.cc:159
bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer.…:
Permission denied (1100)
```

전체 오류: `playwright-status.json`. 실행 스크립트: `../10_browser_check.cjs`.
브라우저 실행이 허용되는 환경에서 저장소 루트에서 다음을 실행하면 390×844 임베드와 1440×900 단독 화면의 정상·가격 인상·다른 판매처 거절 세 흐름을 촬영한다.

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node codex/10_browser_check.cjs
```

이 스크립트는 로컬 파일을 Playwright 라우팅으로 제공하고 `/api/pay/recheck`에는 503을 반환해 **실제 저장값 폴백 경로**를 사용한다. 외부 결제는 발생하지 않는다. 단계별 화면과 모바일 전체 스크롤을 촬영하고 가로 넘침·페이지 오류도 검사한다. 현재 환경에서는 브라우저 시작 전 실패했으므로 이 픽셀 검사는 실행되지 않았다.

## README 표 교체용 파일명 목록

아래는 **재촬영 시 생성할 파일명**이다. 현재 존재하는 PNG로 오해하지 않도록 유의한다. `agentic-pay/README.md`와 기존 `agentic-pay/docs/screens/`는 수정하지 않았다. 총괄이 촬영 결과를 확인하고 복사·교체한다.

| README의 기존 파일 | 교체할 촬영 파일 (`codex/10_shots/`) |
|---|---|
| `docs/screens/01_plan.png` | `1440-01_plan.png` |
| `docs/screens/02_mandates.png` | `1440-02_mandates.png` |
| `docs/screens/03_recheck.png` | `1440-03_recheck.png` |
| `docs/screens/04_quote.png` | `1440-04_quote.png` |
| `docs/screens/04b_price_stop.png` | `1440-04b_price_stop.png` |
| `docs/screens/05_paid_and_rejected.png` | `1440-05_paid_and_rejected.png` |
| `docs/screens/mobile_quote.png` | `390-04_quote.png` |

추가 산출 예정: 각 접두사 `390-` / `1440-`마다 `05_paid.png`, `04c_reapproved.png`, `05_price_paid.png`. 모든 단계는 두 뷰포트에서 생성된다.

## 대신 수행한 검증

- `dom-results.json`: jsdom 화면에 **수정하지 않은 실제 엔진**을 연결해 5개 시나리오 묶음 통과.
- 정상 결제 70,000원, 1초 미만 승인 취소, 초 단위 만료 표시가 길게 누르기 버튼을 교체하지 않는지, 저장값 폴백, 영수증·판매자 해시 일치, 다른 판매처 거절 및 추가 결제 없음.
- 가격 인상 38,000원 → 버튼 잠금 → 두 사람 재위임 → 76,000원 결제.
- 실시간 API 응답 분기와 `window.TRIPFIT_PAY_INPUT`의 외부 이름·상품·16:30·42,000원 지원.
- 위임 만료 시 잠금 → 새 기한으로 재위임.
- 예약 불가 시 빨간 검사·잠긴 결제 버튼·다른 시각 선택 안내.
- 필수 엔진 25/25, 라우터 12/12, JS 문법 검사 통과. 자세한 실행 결과는 `verification.txt`.

DOM 검사에는 레이아웃 엔진이 없다. 실제 픽셀 넘침, CDN 글꼴 로딩, 터치 포인터 길게 누르기, 스프링/도장 애니메이션, 해시 클립보드 복사는 브라우저에서 확인하지 못했다. 실시간 외부 API 호출도 이번 검증에서는 하지 않았다.
