#!/usr/bin/env bash
# 秋招雷达 JobRadar 一键启动（Git Bash / WSL）
set -e
cd "$(dirname "$0")"

PY=""
for cand in ".venv/Scripts/python.exe" ".venv/bin/python" \
            "E:/AIProject/environment/job-radar-venv/Scripts/python.exe"; do
  [ -x "$cand" ] && PY="$cand" && break
done

if [ -z "$PY" ]; then
  echo "[错误] 未找到项目虚拟环境，请先创建："
  echo "  python -m venv E:/AIProject/environment/job-radar-venv"
  echo "  E:/AIProject/environment/job-radar-venv/Scripts/python.exe -m pip install -r requirements.txt"
  exit 1
fi

echo "使用解释器: $PY"
echo "浏览器访问: http://127.0.0.1:8000  （Ctrl+C 停止）"
exec "$PY" main.py serve
