# 🌐 Streamlit Cloud 배포 가이드

## 1. GitHub에 코드 푸시

```bash
cd super-sports-stats-model
git init
git add .
git commit -m "Initial commit - Super Sports Stats Model"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/super-sports-stats-model.git
git push -u origin main
```

## 2. Streamlit Cloud 배포

1. https://streamlit.io/cloud 에 접속
2. GitHub 계정으로 로그인
3. "New app" 클릭
4. Repository 선택: `YOUR_USERNAME/super-sports-stats-model`
5. Main file path: `webapp/app.py`
6. Deploy!

## 3. 무료 티어 한계

- **CPU**: 1 vCPU
- **Memory**: 1 GB RAM
- **Storage**: 1 GB
- **Uptime**: 자동 슬립 (7일간 접속 없으면 슬립)
- **Wake**: 접속 시 10~30초 소요

## 4. 대안 (다른 무료 호스팅)

| 서비스 | 장점 | 단점 |
|--------|------|------|
| **Streamlit Cloud** | Python-native, 쉬움 | 슬립 있음 |
| **Render** | 24/7 무료 (web service) | 빌드 느림 |
| **Railway** | 간단함 | $5 크레딧 후 유료 |
| **PythonAnywhere** | Python 특화 | UI 구림 |
| **Vercel** | 빠름, 24/7 | Static만 무료 |

## 5. 로컬 실행

```bash
cd super-sports-stats-model/webapp
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 http://localhost:8501 접속
