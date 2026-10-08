#!/usr/bin/env bash
# 同时启动网页与单个采集进程；任一进程退出时清理另一个，避免后台残留。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "请先运行 bash scripts/setup.sh" >&2
  exit 1
fi
# 更新代码后的新迁移也在启动时应用，避免新页面访问尚未添加的字段。
bash scripts/start_postgres.sh
.venv/bin/python manage.py migrate --noinput
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
# macOS 自带 Bash 3.2 没有 wait -n；轮询存活状态并保留退出码。
while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 0.5
done
if ! kill -0 "$worker_pid" 2>/dev/null; then
  wait "$worker_pid"
else
  wait "$web_pid"
fi
status=$?
exit "$status"
