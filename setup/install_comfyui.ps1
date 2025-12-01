# ============================================
# ComfyUI 설치 스크립트 (Windows PowerShell)
# AI 이미지/영상 제작 서비스용
# ============================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ComfyUI 설치 스크립트 시작" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 설치 경로 설정
$INSTALL_PATH = "D:\AI_Tools\ComfyUI"
$MODELS_PATH = "$INSTALL_PATH\models"

# Python 확인
Write-Host "[1/6] Python 설치 확인 중..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python이 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host "https://www.python.org/downloads/ 에서 Python 3.10.x를 설치해주세요." -ForegroundColor Red
    exit 1
}
Write-Host "Python 발견: $pythonVersion" -ForegroundColor Green

# Git 확인
Write-Host "[2/6] Git 설치 확인 중..." -ForegroundColor Yellow
$gitVersion = git --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Git이 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host "https://git-scm.com/downloads 에서 Git을 설치해주세요." -ForegroundColor Red
    exit 1
}
Write-Host "Git 발견: $gitVersion" -ForegroundColor Green

# 설치 디렉토리 생성
Write-Host "[3/6] 설치 디렉토리 생성 중..." -ForegroundColor Yellow
if (!(Test-Path $INSTALL_PATH)) {
    New-Item -ItemType Directory -Path $INSTALL_PATH -Force | Out-Null
    Write-Host "디렉토리 생성: $INSTALL_PATH" -ForegroundColor Green
} else {
    Write-Host "디렉토리 이미 존재: $INSTALL_PATH" -ForegroundColor Green
}

# ComfyUI 클론
Write-Host "[4/6] ComfyUI 다운로드 중..." -ForegroundColor Yellow
Set-Location $INSTALL_PATH
if (!(Test-Path "$INSTALL_PATH\.git")) {
    git clone https://github.com/comfyanonymous/ComfyUI.git .
    Write-Host "ComfyUI 다운로드 완료" -ForegroundColor Green
} else {
    Write-Host "ComfyUI 이미 설치됨, 업데이트 중..." -ForegroundColor Yellow
    git pull
}

# 가상환경 생성 및 패키지 설치
Write-Host "[5/6] Python 가상환경 및 패키지 설치 중..." -ForegroundColor Yellow
if (!(Test-Path "$INSTALL_PATH\venv")) {
    python -m venv venv
}

# 가상환경 활성화 및 패키지 설치
& "$INSTALL_PATH\venv\Scripts\Activate.ps1"

Write-Host "PyTorch 설치 중 (CUDA 12.1)..." -ForegroundColor Yellow
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

Write-Host "ComfyUI 의존성 설치 중..." -ForegroundColor Yellow
pip install -r requirements.txt

# 추가 유용한 패키지
pip install opencv-python pillow numpy scipy

Write-Host "[6/6] 모델 디렉토리 구조 생성 중..." -ForegroundColor Yellow

# 모델 디렉토리 구조 생성
$modelDirs = @(
    "$MODELS_PATH\checkpoints",
    "$MODELS_PATH\vae",
    "$MODELS_PATH\loras",
    "$MODELS_PATH\controlnet",
    "$MODELS_PATH\upscale_models",
    "$MODELS_PATH\embeddings",
    "$MODELS_PATH\clip"
)

foreach ($dir in $modelDirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ComfyUI 설치 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "다음 단계:" -ForegroundColor Cyan
Write-Host "1. SDXL 모델 다운로드: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0" -ForegroundColor White
Write-Host "2. 모델을 $MODELS_PATH\checkpoints 에 저장" -ForegroundColor White
Write-Host "3. 실행: run_comfyui.bat" -ForegroundColor White
Write-Host ""
