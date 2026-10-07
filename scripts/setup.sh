#!/usr/bin/env bash
# 可重复执行：安装固定版本依赖并应用数据库迁移，不创建默认密码或演示数据。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
