# 🛠️ AI Studio 자동화 도구 사용 가이드

## 📁 폴더 구조

```
tools/
├── batch_image_processor.py    # 이미지 배치 처리 도구
├── requirements.txt            # Python 패키지 목록
└── README.md                   # 이 파일
```

---

## 🚀 설치 방법

### 1. Python 가상환경 생성 (권장)

```powershell
cd D:\aiproject\projecta\tools
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. 패키지 설치

```powershell
pip install -r requirements.txt
```

---

## 📸 이미지 배치 처리 도구

### 기본 사용법

```powershell
python batch_image_processor.py <입력경로> [옵션]
```

### 프리셋 사용

| 프리셋 | 설명 | 출력 |
|--------|------|------|
| `smartstore` | 스마트스토어 상세페이지용 | 1000px, JPG |
| `thumbnail` | 썸네일 생성 | 300x300, JPG |
| `youtube` | 유튜브 썸네일 | 1280x720, PNG |
| `instagram` | 인스타그램 피드 | 1080px, JPG |
| `webp` | 웹 최적화 | WebP 변환 |
| `4k` | 고해상도 | 3840px, PNG |

### 예시

```powershell
# 스마트스토어용 최적화
python batch_image_processor.py D:\작업\이미지폴더 --preset smartstore

# 유튜브 썸네일 크기로 변환
python batch_image_processor.py D:\작업\이미지폴더 --preset youtube

# WebP로 변환 (용량 절약)
python batch_image_processor.py D:\작업\이미지폴더 --preset webp

# 커스텀 크기로 리사이즈
python batch_image_processor.py D:\작업\이미지폴더 --width 800 --format jpg

# 출력 폴더 지정
python batch_image_processor.py D:\작업\이미지폴더 --preset smartstore -o D:\출력폴더

# 워터마크 추가
python batch_image_processor.py D:\작업\이미지폴더 --watermark "AI Studio"
```

### 옵션 설명

| 옵션 | 설명 |
|------|------|
| `-o, --output` | 출력 폴더 경로 |
| `-p, --preset` | 프리셋 선택 |
| `-w, --width` | 리사이즈 너비 (px) |
| `-H, --height` | 리사이즈 높이 (px) |
| `-s, --scale` | 스케일 배율 (예: 0.5, 2.0) |
| `-f, --format` | 출력 포맷 (jpg, png, webp) |
| `--watermark` | 워터마크 텍스트 |

---

## 💡 작업 팁

### 1. 스마트스토어/쿠팡 이미지 규격

```powershell
# 상세페이지 이미지 (권장: 860~1000px)
python batch_image_processor.py ./원본이미지 --preset smartstore

# 대표 이미지 (정사각형)
python batch_image_processor.py ./원본이미지 --width 500 --height 500 -f jpg
```

### 2. SNS용 이미지

```powershell
# 인스타그램 피드 (정사각형)
python batch_image_processor.py ./원본이미지 --width 1080 --height 1080 -f jpg

# 인스타그램 스토리 (세로)
python batch_image_processor.py ./원본이미지 --width 1080 --height 1920 -f jpg
```

### 3. 웹 최적화 (용량 절약)

```powershell
# WebP 변환 (원본 대비 30~50% 용량 절약)
python batch_image_processor.py ./원본이미지 --preset webp
```

---

## ⚠️ 주의사항

1. **원본 보존**: 출력은 항상 새 폴더에 저장됩니다 (원본 손상 없음)
2. **JPEG 변환**: 투명 배경이 있는 PNG를 JPEG로 변환 시 흰색 배경으로 대체됩니다
3. **대용량 처리**: 수백 장 이상 처리 시 시간이 걸릴 수 있습니다

---

## 🔧 문제 해결

### Pillow 설치 오류

```powershell
pip install --upgrade pip
pip install Pillow --force-reinstall
```

### 한글 경로 문제

- 가능하면 영문 경로 사용 권장
- 또는 경로를 따옴표로 감싸기: `"D:\작업\한글폴더"`

---

## 📞 지원

문제가 있으면 이슈를 등록하거나 contact@aistudio.kr로 문의하세요.
