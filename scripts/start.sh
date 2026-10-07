#!/usr/bin/env bash
# 同时启动网页与单个采集进程；任一进程退出时清理另一个，避免后台残留。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "请先运行 bash scripts/setup.sh" >&2
  exit 1
fi
.venv/bin/python manage.py check
.venv/bin/python manage.py collect_worker &
worker_pid=$!
.venv/bin/python manage.py runserver "${SHOPHOT_BIND:-127.0.0.1:8000}" --noreload &
web_pid=$!
cleanup() {
  kill "$worker_pid" "$web_pid" 2>/dev/null || true
  wait "$worker_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
set +e
wait -n "$worker_pid" "$web_pid"
status=$?
exit "$status"
