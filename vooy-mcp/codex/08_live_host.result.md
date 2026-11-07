`/chat`을 실제 `/mcp`와 통신하는 데모 호스트로 구현했습니다.

- **변경:** `hapui/server.py`, `hapui/text.py`, `ui/board.html`, `ui/chat.html`, `ui/README.md`, `tests/test_chat.py`, `tests/test_text.py`
- **요청 순서:** `initialize` → `notifications/initialized` → `tools/list` → `resources/read` → `tools/call`
- **위젯:** 도구 메타데이터의 `ui://` 리소스를 읽고 MIME을 확인합니다. 받은 HTML의 nonce를 부모 nonce로 맞춰 `sandbox="allow-scripts"`의 `srcdoc`으로 표시합니다.
- **동작:** 자동 대본, 직접 입력, 예산 양보, 조건 충돌, 위젯 액션 전달, 새 카드 추가, 오류 재시도와 호출 로그를 구현했습니다.
- **삭제:** 기존 `ui/preview.html`, fixture JSON 3개, `scripts/make_fixtures.py`
- **검증:** pytest **60개 통과**, JS 구문 검사 통과, 보안 및 금지 문장부호 grep **0건**. DOM과 실제 TestClient MCP를 연결한 흐름 검증도 통과했습니다.

**미확인:** 포트 열기가 차단되어 curl 검증은 TestClient로 대체했습니다. Chrome 실행 제한과 도구 접근 미승인으로 실제 브라우저의 CSP 집행 및 시각 검증은 완료하지 못했습니다.