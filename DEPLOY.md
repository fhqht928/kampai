# 🚀 Kampai 배포 가이드

## 📋 구조

```
projecta/
├── website-prod/     # 프론트엔드 (배포용) → Vercel
├── website-dev/      # 프론트엔드 (개발용)
├── backend/          # Flask API → Railway
└── ...
```

---

## 🌐 방법 1: Vercel + Railway (추천)

### Step 1: GitHub 저장소 생성

```bash
# 이미 git init 완료됨
cd D:\aiproject\projecta

# GitHub에서 새 저장소 생성 후
git remote add origin https://github.com/YOUR_USERNAME/kampai.git
git branch -M main
git push -u origin main
```

### Step 2: Vercel에 프론트엔드 배포

1. [vercel.com](https://vercel.com) 가입/로그인
2. "Add New Project" 클릭
3. GitHub 연결 → kampai 저장소 선택
4. 설정:
   - **Root Directory**: `website-prod`
   - **Framework**: Other
5. "Deploy" 클릭

배포 후 URL: `https://kampai-xxxxx.vercel.app`

### Step 3: Railway에 백엔드 배포

1. [railway.app](https://railway.app) 가입/로그인
2. "New Project" → "Deploy from GitHub repo"
3. kampai 저장소 선택
4. 설정:
   - **Root Directory**: `backend`
5. **Environment Variables** 설정:
   ```
   REPLICATE_API_TOKEN=r8_xxxxxxxxxxxxxx
   KAMPAI_ENV=production
   JWT_SECRET=your-secret-key-here
   TOSS_SECRET_KEY=test_sk_xxxxxx (선택)
   ```
6. "Deploy" 클릭

배포 후 URL: `https://kampai-backend-production.up.railway.app`

### Step 4: 프론트엔드 API URL 수정

`website-prod/generate.html`에서 API_URL을 Railway URL로 변경:

```javascript
// 변경 전
const API_URL = 'http://localhost:5000';

// 변경 후
const API_URL = 'https://kampai-backend-production.up.railway.app';
```

---

## 💰 예상 비용

| 서비스 | 무료 티어 | 유료 |
|--------|----------|------|
| Vercel | 100GB/월 | $20/월~ |
| Railway | $5 크레딧/월 | $5/월~ |
| Replicate | 종량제 | $0.003~0.05/이미지 |

**월 예상 비용**: $5~20 (트래픽에 따라)

---

## 🔧 환경 변수 목록

### 필수
| 변수 | 설명 |
|------|------|
| `REPLICATE_API_TOKEN` | Replicate API 키 |
| `JWT_SECRET` | JWT 서명 키 (임의 문자열) |

### 선택
| 변수 | 설명 | 기본값 |
|------|------|--------|
| `KAMPAI_ENV` | 환경 설정 | development |
| `PORT` | 서버 포트 | 5000 |
| `TOSS_SECRET_KEY` | 토스페이먼츠 키 | - |

---

## 🖥️ 방법 2: 로컬 서버 직접 운영

### Ngrok으로 터널링 (테스트용)

```powershell
# 1. ngrok 설치
winget install ngrok

# 2. 백엔드 터널링
ngrok http 5000

# 3. 프론트엔드 터널링 (Live Server 사용 시)
ngrok http 5500
```

### 도메인 연결 (운영용)

1. 도메인 구매 (가비아, 카페24 등) - 약 15,000원/년
2. Cloudflare 무료 CDN 연결
3. 자체 서버 또는 클라우드 VM 사용

---

## 🔄 CI/CD 자동 배포

GitHub에 push하면 자동 배포됩니다:

```bash
# 변경사항 커밋 & 푸시
git add .
git commit -m "Update feature"
git push

# Vercel & Railway가 자동으로 재배포
```

---

## ✅ 배포 체크리스트

- [ ] GitHub 저장소 생성
- [ ] Replicate API 토큰 발급
- [ ] Vercel 프론트엔드 배포
- [ ] Railway 백엔드 배포
- [ ] 환경 변수 설정
- [ ] API_URL 수정
- [ ] CORS 설정 확인
- [ ] HTTPS 적용 확인
- [ ] 결제 테스트 (토스페이먼츠)

---

## 🆘 문제 해결

### CORS 오류
Railway 환경변수에 추가:
```
ALLOWED_ORIGINS=https://your-vercel-url.vercel.app
```

### API 연결 실패
1. Railway 로그 확인
2. 환경변수 설정 확인
3. API URL 올바른지 확인

### 이미지 생성 실패
1. Replicate 토큰 유효한지 확인
2. Replicate 크레딧 확인
3. 모델 이름 올바른지 확인
