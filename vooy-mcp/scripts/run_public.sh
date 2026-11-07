#!/bin/sh
# Configure HAPUI_PUBLIC_HOST/URL to the tunnel's assigned host before connecting vooy.
set -eu
cd "$(dirname "$0")/.."
port="${PORT:-8765}"
command -v ngrok >/dev/null 2>&1 || { echo 'ngrok을 설치한 환경에서 실행해 주세요.' >&2; exit 1; }
.venv/bin/python -m hapui.server --port "$port" &
server_pid=$!
ngrok_pid=''
cleanup() {
  kill "$server_pid" 2>/dev/null || true
  if [ -n "$ngrok_pid" ]; then kill "$ngrok_pid" 2>/dev/null || true; fi
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
ngrok http "$port" &
ngrok_pid=$!
wait "$ngrok_pid"
