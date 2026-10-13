@echo off
chcp 65001 >nul
title Qastroute AI Gateway
echo ============================================================
echo   🚀 STARTING QASTROUTE AI GATEWAY
echo   Universal Multi-Model Gateway & Smart Cost-Optimizer
echo ============================================================
echo.
cd /d "C:\Users\ASUS\Projects\qastroute_ai"
echo [*] Web Dashboard: http://localhost:8000
echo [*] API Endpoints: /v1/chat/completions ^& /v1/messages
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
