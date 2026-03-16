#!/bin/bash
echo "🚀 서버 시작 중..."
cd "$(dirname "$0")/backend" && python3 -m uvicorn main:app --reload --port 8000 &
sleep 2
echo "✅ 서버 실행 중"
open "$(dirname "$0")/index.html"
wait
