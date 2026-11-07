구현했습니다.

- **변경/추가 7개 파일:** `ui/board.html`, `ui/preview.html`, `ui/README.md`, `scripts/make_fixtures.py`, `ui/fixtures/real_{propose,yield,infeasible}.json`
- **대화 카드:** 투명 문서 배경, 사람·코스 한 줄 요약, `+N` 처리. 300/360px에서 약 **360–400px 예상**이며 실측은 미확인입니다.
- **모드 전환:** inline 카드와 fullscreen 전체 보드가 상태·선택한 안을 공유합니다. 확대 거절 시 웹 링크로 연결하고, 링크도 없으면 버튼을 숨깁니다.
- **모션:** 200ms 카드 등장, 300ms 막대·숫자 갱신, 코스 FLIP·하이라이트·접힘, 계산 중 점 표시, reduced motion 대응.
- **검증:** pytest **54 passed**, Node 구문 검사 통과, 요청한 보안 grep **0건**, DOM 검사 141개 단언 통과.

미리보기 실행:

```sh
cd ui && python3 -m http.server 8791
```

`http://localhost:8791/preview.html`에서 **다음 대화 재생**을 누르면 기존 iframe이 예산 양보 결과로 갱신됩니다.

환경의 소켓·브라우저 접근 제한으로 실제 화면 크기·넘침·모션·스크린샷과 vooy 실호스트 연동은 확인하지 못했습니다.