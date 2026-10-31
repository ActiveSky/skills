#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "需要 uv：https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  uv venv "$ROOT/.venv"
fi

uv pip install --python "$ROOT/.venv/bin/python" -r "$ROOT/requirements.txt"

echo "Vendored yuque-cli ready."
echo "Run: $ROOT/scripts/yuque.sh --help"
