구현했습니다. 변경 파일은 `web/pay/index.html`, `app.js`, `styles.css`와 `codex/10_*` 검증·인계 파일입니다. 엔진·API·서버는 수정하지 않았습니다.

1. **일정**: 장소 블록, violet 해칭 결제 대상, 현장 결제 구분.
2. **위임**: pink·sky 카드, 큰 상한 금액, 1초 승인 링·체크 도장.
3. **예약**: 아일랜드 알림, 조회 내역·출처, 접힌 문의 초안.
4. **결제 전**: 검사 6개, 실패 시 잠금·복구 안내, 가격 변화·재위임, 분담·합계와 승인 후 동작.
5. **완료**: 승인번호, 해시 복사, 판매자 전달 내용, 예약 링크·판매처 거절 결과.

검사 6개는 다음 엔진 값에서 계산합니다.

| 검사 | 엔진 근거 |
|---|---|
| 판매처 일치 | `merchant.lookup(scope).merchant_id`, 위임의 `merchant_id` |
| 상품·시각 일치 | lookup의 `item_gid/date/option_start`, 합의 일정, 위임 범위 |
| 가격 ≤ 상한 | `quote.lines[].amount`, `mandate_max` |
| 예약 가능 | lookup의 `available`, `checked_at` |
| 기한 안 | 위임의 `expires_at`, `world.clock.now()` |
| 위임 완료·미사용 | `status`, `uses`, `pay.isMandateUsed(id)` |

전체 검사 통과와 `quote.status === 'READY'`, 모든 `lines[].within`이 충족되어야 승인할 수 있습니다.

**검증:** 엔진 **25/25**, 라우터 **12/12**, JS 문법 검사 통과. 실제 엔진 연결 DOM 검사로 정상·가격 인상 후 재위임·판매처 거절·외부 입력·만료·예약 불가도 확인했습니다.

**스크린샷:** PNG는 생성하지 못했습니다. Chromium이 `MachPortRendezvous … Permission denied (1100)`으로 종료됐습니다. 실패 로그·재촬영 스크립트·README 교체용 파일명 목록은 [촬영 인계 문서](</Users/harheem/Library/Application Support/Claude/scratch-workspaces/8abcbd08-cf49-48d2-a8c8-1227fcb10a42/ea79a99b-4f99-4b96-bb73-f0adf342658a/scratch-2026-11-06-917dcc/tripfit/codex/10_shots/README.md>)에 남겼습니다.

**미확인:** 실제 픽셀 품질·넘침, CDN 글꼴, 터치·애니메이션·클립보드, 외부 실시간 조회.