#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/script/setup_local_whisper.sh"

echo ""
read -k 1 "?安装结束，按任意键关闭窗口…"
