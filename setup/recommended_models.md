# 🎨 추천 AI 모델 목록

> RTX 4060 Ti 16GB에 최적화된 모델 리스트입니다.

---

## 📦 필수 모델 (우선 다운로드)

### 1. Stable Diffusion XL Base
- **용도**: 고품질 이미지 생성의 기본 모델
- **크기**: 약 6.5GB
- **다운로드**: [HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)
- **저장 위치**: `models/checkpoints/`

### 2. SDXL VAE
- **용도**: 이미지 품질 향상
- **크기**: 약 335MB
- **다운로드**: [HuggingFace](https://huggingface.co/stabilityai/sdxl-vae)
- **저장 위치**: `models/vae/`

### 3. SDXL Refiner
- **용도**: 이미지 디테일 향상
- **크기**: 약 6GB
- **다운로드**: [HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0)
- **저장 위치**: `models/checkpoints/`

---

## 🎯 제품 이미지 특화 모델

### 4. Product Photography LoRA
- **용도**: 제품 사진 스타일
- **추천**: Civitai에서 "product photography" 검색
- **저장 위치**: `models/loras/`

### 5. RealVisXL
- **용도**: 사실적인 이미지 생성
- **다운로드**: [Civitai](https://civitai.com/models/139562/realvisxl-v40)
- **저장 위치**: `models/checkpoints/`

---

## 🖼️ 이미지 보정/업스케일 모델

### 6. 4x-UltraSharp
- **용도**: 이미지 업스케일 (4배)
- **크기**: 약 67MB
- **다운로드**: [GitHub](https://github.com/cszn/KAIR)
- **저장 위치**: `models/upscale_models/`

### 7. Real-ESRGAN x4plus
- **용도**: 사실적 이미지 업스케일
- **저장 위치**: `models/upscale_models/`

---

## 🎬 영상 생성 모델

### 8. Stable Video Diffusion
- **용도**: 이미지 → 영상 변환
- **크기**: 약 9GB
- **VRAM 요구**: 12GB+ (16GB 권장)
- **다운로드**: [HuggingFace](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt)

### 9. AnimateDiff
- **용도**: 이미지 애니메이션
- **다운로드**: [HuggingFace](https://huggingface.co/guoyww/animatediff)
- **저장 위치**: `models/animatediff/`

---

## 🎨 ControlNet 모델 (선택)

### 10. ControlNet SDXL
- **용도**: 포즈, 엣지, 깊이 제어
- **종류**:
  - `controlnet-canny-sdxl` - 엣지 검출
  - `controlnet-depth-sdxl` - 깊이 맵
  - `controlnet-openpose-sdxl` - 포즈 제어
- **저장 위치**: `models/controlnet/`

---

## 📋 다운로드 체크리스트

```
필수 모델 (즉시 다운로드):
[ ] SDXL Base 1.0
[ ] SDXL VAE
[ ] 4x-UltraSharp 업스케일러

권장 모델 (1주 내):
[ ] SDXL Refiner
[ ] RealVisXL
[ ] Real-ESRGAN

선택 모델 (필요 시):
[ ] Stable Video Diffusion
[ ] AnimateDiff
[ ] ControlNet 시리즈
```

---

## ⚠️ 주의사항

1. **VRAM 관리**: 16GB VRAM으로 SDXL 기본 실행 가능, 여러 모델 동시 로드 시 주의
2. **저장 공간**: 모든 모델 설치 시 약 50GB 필요
3. **라이선스**: 상업적 사용 가능 여부 확인 필수
   - Stability AI 모델: 상업적 사용 가능 (조건부)
   - Civitai 모델: 개별 라이선스 확인 필요

---

## 🔗 유용한 링크

- [Civitai](https://civitai.com/) - 커뮤니티 모델 허브
- [HuggingFace](https://huggingface.co/) - 공식 모델 저장소
- [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager) - 확장 관리자
