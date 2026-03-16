#!/bin/bash
echo "📦 패키지 설치 중..."
pip install -r requirements.txt -q
echo "🚀 서버 시작 중... 브라우저가 자동으로 열립니다"
python main.py
