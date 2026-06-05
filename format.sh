#!/bin/bash
# 文案排版工具 — 启动脚本
# 运行在端口 8001，独立于 xhs-agent

set -e
cd "$(dirname "$0")"
source .venv/bin/activate
python -m src.format_server
