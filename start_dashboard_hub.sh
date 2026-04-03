#!/bin/bash
# start_dashboard_hub.sh
# Avvia solo API Hub e Dashboard per la gestione della pipeline DIAS

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

# Interpretatore del Virtual Env
PYTHON_BIN="$BASE_DIR/.venv/bin/python3"
export PYTHONPATH="$BASE_DIR"

echo "🌐 Avvio componenti di Magement DIAS (Hub + Dashboard)..."

# 1. Avvio API Hub (Port 8000)
echo "🚀 (Ri)avvio API Hub..."
pkill -f "src.api.main:app" || true
sleep 1
nohup "$PYTHON_BIN" -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/api_hub.log" 2>&1 &
sleep 2

if pgrep -f "src.api.main:app" > /dev/null; then
    echo "   -> API Hub pronto."
else
    echo "   ❌ ERRORE: Fallimento avvio API Hub. Controlla $LOG_DIR/api_hub.log"
fi

# 2. Avvio Dashboard (Port 5173)
echo "🚀 (Ri)avvio Dashboard..."
pkill -f "vite" || true
pkill -f "svelte-kit" || true
sleep 1
cd "$BASE_DIR/src/dashboard" || exit
nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/dashboard.log" 2>&1 &
sleep 3

if pgrep -f "vite" > /dev/null || pgrep -f "svelte-kit" > /dev/null; then
    echo "   -> Dashboard pronta."
else
    echo "   ❌ ERRORE: Fallimento avvio Dashboard. Controlla $LOG_DIR/dashboard.log"
fi
cd "$BASE_DIR"

echo ""
echo "✨ Gestione DIAS pronta."
echo "🔗 Dashboard: http://$(hostname -I | awk '{print $1}'):5173"
echo "🔗 API Hub:   http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "Nota: L'Orchestratore NON è stato avviato. Usa la Dashboard per innescare i task con override voce."
