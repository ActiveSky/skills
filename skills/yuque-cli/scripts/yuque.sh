#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  PY="$HOME/.agents/skills/yuque-cli/.venv/bin/python"
fi

if [ ! -x "$PY" ]; then
  echo "未找到 Python 环境。请先运行 $ROOT/bootstrap.sh" >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/yuque.py" "$@"
