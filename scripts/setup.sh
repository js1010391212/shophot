#!/usr/bin/env bash
# 安装固定依赖并迁移；先保护已有环境，不创建默认账号或演示数据。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
fail() { echo "ShopHot 安装未执行：$1" >&2; exit 1; }
selected_python="${SHOPHOT_PYTHON:-python3}"
[[ "$selected_python" != -* ]] || fail "SHOPHOT_PYTHON 必须是单独的 Python 可执行文件。"
python_command=$(command -v "$selected_python") || fail "找不到所选 Python；请通过 SHOPHOT_PYTHON 指定已安装的 Python 3.12 或以上版本。"
selected_version=$("$python_command" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || fail "所选 Python 无法运行，请核对 SHOPHOT_PYTHON。"
[[ "$selected_version" =~ ^([0-9]+)\.([0-9]+)$ ]] || fail "无法核对所选 Python 版本。"
selected_major="${BASH_REMATCH[1]}"
selected_minor="${BASH_REMATCH[2]}"
(( selected_major > 3 || (selected_major == 3 && selected_minor >= 12) )) || fail "所选 Python ${selected_version} 低于要求的 3.12；请明确选择兼容版本。"
if [[ -e .venv || -L .venv ]]; then
  [[ ! -L .venv && -d .venv && -f .venv/pyvenv.cfg && ! -L .venv/pyvenv.cfg && -x .venv/bin/python ]] || fail "已有 .venv 不是完整的独立虚拟环境；请保留原目录并由维护者核对，脚本不会覆盖或清空它。"
  existing_version=$(.venv/bin/python -c '
import pathlib, re, sys
root = pathlib.Path(".venv").resolve()
if sys.prefix == sys.base_prefix or pathlib.Path(sys.prefix).resolve() != root:
    sys.exit(1)
match = re.search(r"^version\s*=\s*(\d+)\.(\d+)(?:\.\d+)?\s*$", (root / "pyvenv.cfg").read_text(), re.M)
if not match or tuple(map(int, match.groups())) != sys.version_info[:2]:
    sys.exit(1)
print("%d.%d" % sys.version_info[:2])
' 2>/dev/null) || fail "已有 .venv 无法运行或配置与实际 Python 不一致；请保留原环境并由维护者检查。"
  [[ "$existing_version" == "$selected_version" ]] || fail "已有 .venv 使用 Python ${existing_version}，所选版本为 ${selected_version}；主次版本不同，未写环境、安装依赖或迁移。请保留原环境并明确选择相同版本，或另建隔离目录。"
else
  "$python_command" -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
