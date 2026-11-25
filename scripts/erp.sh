#!/bin/sh
# Linux entry point without activation or a global python alias.
set -eu
erp_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
erp_python="$erp_root/plugins/core/backend/.venv/bin/python"
if [ ! -f "$erp_python" ]; then
    printf '%s\n' '请先创建 plugins/core/backend/.venv 并安装 plugins/core/backend/requirements.txt 中的依赖。' >&2
    exit 2
fi
exec "$erp_python" "$erp_root/scripts/erp.py" "$@"
