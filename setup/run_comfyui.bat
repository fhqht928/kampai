@echo off
echo ========================================
echo   ComfyUI 실행
echo ========================================
echo.

cd /d D:\AI_Tools\ComfyUI
call C:\Users\fhqht\miniconda3\Scripts\activate.bat comfyui

echo ComfyUI를 시작합니다...
echo 브라우저에서 http://127.0.0.1:8188 로 접속하세요
echo.

python main.py --listen --port 8188

pause
