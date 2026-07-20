#!/bin/zsh
set -e
cd "$(dirname "$0")"
echo "检查视频分析工作流..."
uv run video-agent doctor
echo ""
echo "示例："
echo "  uv run video-agent prepare /路径/视频.mp4"
echo "  uv run video-agent analyze /路径/视频.mp4 -q '按时间线分析这个视频'"
echo ""
exec /bin/zsh
