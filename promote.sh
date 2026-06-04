#!/bin/bash
# xhs-agent novel promoter — quick wrapper
#
# Usage: ./promote.sh <chapter_file> [platform] [--no-review] [--use-llm]
#
# Examples:
#   ./promote.sh "第3章-石门.md"                          # 小红书，默认配置
#   ./promote.sh "第3章-石门.md" xiaohongshu --no-review  # 跳过审核
#   ./promote.sh "第3章-石门.md" douyin --use-llm         # 抖音 + LLM策略

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CHAPTER="${1:?请指定章节文件路径}"
PLATFORM="${2:-xiaohongshu}"
EXTRA_ARGS="${@:3}"

# Ensure Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "🔧 启动 Ollama..."
    ~/.ollama/bin/bin/ollama serve &>/dev/null &
    sleep 3
fi

# Activate venv and run
source .venv/bin/activate
python -m src.main novel promote \
    -c "$CHAPTER" \
    --profile data/novel_profile.json \
    -p "$PLATFORM" \
    $EXTRA_ARGS
