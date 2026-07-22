# ============================================================
# Super Sports Stats Model - 자동 배포 스크립트
# Oracle Cloud / Ubuntu 용
# GitHub: https://github.com/coohell/super-sports-stats-model
# ============================================================

#!/bin/bash
set -e

APP_DIR="$HOME/super-sports-stats-model"
PORT="80"
REPO_URL="https://github.com/coohell/super-sports-stats-model.git"

echo "🚀 Super Sports Stats Model 배포 시작..."

# 1. 시스템 업데이트
echo "📦 시스템 업데이트 중..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv git nginx

# 2. 기존 정리
echo "🧹 기존 프로세스 정리..."
pkill -f "streamlit run" 2>/dev/null || true
sudo systemctl stop super-sports-stats 2>/dev/null || true

# 3. 프로젝트 클론
echo "📥 GitHub에서 프로젝트 클론..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 4. 가상환경
echo "🐍 Python 가상환경 설정..."
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate

# 5. 의존성
echo "📦 Python 패키지 설치..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q -r webapp/requirements.txt 2>/dev/null || true

# 6. Streamlit 설정
echo "🔧 Streamlit 설정..."
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml << EOF
[server]
headless = true
port = $PORT
enableCORS = false
enableXsrfProtection = false

[theme]
primaryColor = "#667eea"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
EOF

# 7. 방화벽
echo "🔥 방화벽 설정..."
sudo ufw allow 80/tcp 2>/dev/null || true
sudo ufw allow 443/tcp 2>/dev/null || true

# 8. systemd 서비스
echo "🔌 systemd 서비스 등록..."
sudo tee /etc/systemd/system/super-sports-stats.service > /dev/null << EOF
[Unit]
Description=Super Sports Stats Model
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/webapp
Environment="PATH=$APP_DIR/venv/bin"
Environment="PYTHONPATH=$APP_DIR"
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.port=$PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable super-sports-stats.service
sudo systemctl restart super-sports-stats.service

# 9. Nginx (선택)
echo "🌐 Nginx 설정..."
sudo tee /etc/nginx/sites-available/super-sports-stats > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;
    location / {
        proxy_pass http://localhost:80;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/super-sports-stats /etc/nginx/sites-enabled/ 2>/dev/null || true
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t 2>/dev/null && sudo systemctl restart nginx 2>/dev/null || true

# 10. 완료
echo ""
echo "========================================"
echo "✅ 배포 완료!"
echo "========================================"
echo "🌐 http://$(curl -s ifconfig.me 2>/dev/null || echo '서버IP')"
echo ""
echo "📊 상태: sudo systemctl status super-sports-stats"
echo "🔄 재시작: sudo systemctl restart super-sports-stats"
echo "📜 로그: sudo journalctl -u super-sports-stats -f"
echo "========================================"
