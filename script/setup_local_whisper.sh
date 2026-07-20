#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODEL_DIR="$PROJECT_ROOT/models"
MODEL_PATH="$MODEL_DIR/ggml-large-v3-turbo.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
MODEL_SHA1="4af2b29d7ec73d781377bfd1758ca957a807e941"

if ! command -v brew >/dev/null 2>&1; then
    echo "没有找到 Homebrew。请先安装 Homebrew，再重新运行此安装器。"
    exit 1
fi

if ! command -v whisper-cli >/dev/null 2>&1; then
    echo "正在安装免费的本地听觉引擎 whisper.cpp…"
    brew install whisper-cpp
else
    echo "whisper.cpp 已安装。"
fi

mkdir -p "$MODEL_DIR"
if [[ ! -f "$MODEL_PATH" ]] || [[ "$(shasum -a 1 "$MODEL_PATH" | awk '{print $1}')" != "$MODEL_SHA1" ]]; then
    echo "正在下载准确率更高的 large-v3-turbo 多语言模型（约 1.5 GB）…"
    curl --fail --location --progress-bar "$MODEL_URL" --output "$MODEL_PATH.download"
    ACTUAL_SHA1="$(shasum -a 1 "$MODEL_PATH.download" | awk '{print $1}')"
    if [[ "$ACTUAL_SHA1" != "$MODEL_SHA1" ]]; then
        echo "模型校验失败，下载文件不完整。请重新运行安装器。"
        exit 1
    fi
    mv "$MODEL_PATH.download" "$MODEL_PATH"
else
    echo "large-v3-turbo 模型已存在并通过校验。"
fi

echo ""
echo "安装完成：$MODEL_PATH"
echo "现在可在视频分析台设置中选择「本地 Whisper（免费、不上传）」。"
