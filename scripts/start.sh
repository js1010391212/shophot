#!/usr/bin/env bash
# 标准库 supervisor 在任何数据库/迁移/子进程之前保护本项目启动。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "请先运行 bash scripts/setup.sh" >&2
  exit 1
fi
exec .venv/bin/python config/local_runtime.py
