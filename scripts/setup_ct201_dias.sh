#!/bin/bash
# setup_ct201_dias.sh
# Setup CT201 come DIAS Runtime (API Hub + Svelte Dashboard build)
# Eseguire sul container come root dopo il primo boot.
#
# Uso: bash setup_ct201_dias.sh <GITHUB_TOKEN>
# Esempio: bash setup_ct201_dias.sh ghp_xxx...
#
# Il token GitHub si recupera da NH-Mini:
#   python3 scripts/credential_manager.py --service github --key main --get

set -euo pipefail

GITHUB_TOKEN="${1:-}"
REPO_OWNER="S3ph1r"
REPO_NAME="dias-project"
INSTALL_DIR="/opt/dias"
APP_BASE_PATH="/dias"
REDIS_HOST="192.168.1.120"
REDIS_PORT="6379"

# ─── Validazione ──────────────────────────────────────────────────────────────

if [[ -z "$GITHUB_TOKEN" ]]; then
    echo "❌ GitHub token richiesto."
    echo "   Uso: bash $0 <GITHUB_TOKEN>"
    echo "   Da NH-Mini: python3 scripts/credential_manager.py --service github --key main --get"
    exit 1
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  CT201 — DIAS Runtime Setup                             ║"
echo "║  FastAPI API Hub + SvelteKit Dashboard (static build)   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ─── 1. Dipendenze di sistema ─────────────────────────────────────────────────

echo "📦 [1/6] Installazione dipendenze di sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

# Python + build tools
apt-get install -y -qq python3 python3-venv python3-dev build-essential git curl

# Audio processing (richiesto da Stage E e audio_utils)
apt-get install -y -qq sox ffmpeg libsndfile1

# Node.js 20.x (LTS) per build SvelteKit
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
apt-get install -y -qq nodejs

echo "   ✅ Sistema pronto (Python $(python3 --version | cut -d' ' -f2), Node $(node --version))"

# ─── 2. Clone repository ──────────────────────────────────────────────────────

echo "📦 [2/6] Clone repository DIAS..."
rm -rf "$INSTALL_DIR"
git clone --depth=1 \
    "https://${GITHUB_TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git" \
    "$INSTALL_DIR" 2>&1 | tail -3
echo "   ✅ Repository clonato in $INSTALL_DIR"

# ─── 3. Python venv + dipendenze ─────────────────────────────────────────────

echo "📦 [3/6] Creazione venv Python e installazione dipendenze..."
cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "   ✅ Python venv pronto"

# ─── 4. Build SvelteKit (static) ──────────────────────────────────────────────

echo "📦 [4/6] Build SvelteKit dashboard..."
cd "$INSTALL_DIR/src/dashboard"

# Installa adapter-static se non già presente
if ! grep -q "adapter-static" package.json 2>/dev/null; then
    npm install --silent @sveltejs/adapter-static --save-dev
fi

npm install --silent
PUBLIC_BASE_PATH="$APP_BASE_PATH" npm run build 2>&1 | tail -5

if [[ -f "$INSTALL_DIR/src/dashboard/build/index.html" ]]; then
    echo "   ✅ Build SvelteKit completata → src/dashboard/build/"
else
    echo "   ❌ Build fallita. Controlla gli errori sopra."
    exit 1
fi

# ─── 5. Configurazione .env ───────────────────────────────────────────────────

echo "📦 [5/6] Creazione .env..."
cd "$INSTALL_DIR"
cat > .env << EOF
DIAS_REDIS_HOST=${REDIS_HOST}
DIAS_REDIS_PORT=${REDIS_PORT}
DIAS_REDIS_DB=0
DIAS_APP_BASE=${APP_BASE_PATH}
EOF
echo "   ✅ .env creato"

# ─── 6. Systemd service ───────────────────────────────────────────────────────

echo "📦 [6/6] Configurazione systemd..."
cat > /etc/systemd/system/dias-api.service << EOF
[Unit]
Description=DIAS API Hub
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn src.api.main:app \\
    --host 0.0.0.0 \\
    --port 8000 \\
    --root-path ${APP_BASE_PATH}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable dias-api
systemctl start dias-api
sleep 3

if systemctl is-active --quiet dias-api; then
    echo "   ✅ dias-api in esecuzione"
else
    echo "   ⚠️  dias-api non avviato — controlla: journalctl -u dias-api -n 30"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ CT201 DIAS Runtime pronto"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔗 Locale:    http://192.168.1.201:8000"
echo "🌐 Via ngrok: https://obliging-fitting-cheetah.ngrok-free.app/dias/"
echo ""
echo "📁 Installazione: $INSTALL_DIR"
echo "📋 Log:           journalctl -u dias-api -f"
echo "🔧 Restart:       systemctl restart dias-api"
echo ""
echo "⚠️  La data/ directory è vuota — i progetti vanno caricati"
echo "   dalla dashboard via Upload."
