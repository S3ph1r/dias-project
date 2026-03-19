#!/bin/bash
# start_pipeline.sh
# Avvia i worker della pipeline DIAS in background su LXC 201

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$BASE_DIR/logs"

mkdir -p "$LOG_DIR"

echo "🚀 Avvio della Pipeline DIAS (A, B, C, D)..."
cd "$BASE_DIR" || exit
export PYTHONPATH="$BASE_DIR"

# Interpretatore del Virtual Env
PYTHON_BIN="$BASE_DIR/.venv/bin/python3"

# --- SECURITY GUARD ---
# Verifica se l'orchestratore è già attivo per evitare duplicati
if pgrep -f "src/common/orchestrator.py" > /dev/null; then
    echo "❌ ERRORE: Un'istanza dell'Orchestratore è già in esecuzione!"
    echo "Esegui prima ./stop_pipeline.sh per pulire i vecchi processi."
    exit 1
fi
# ----------------------

# API Hub
echo "  -> Avvio API Hub (Port 8000)..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    nohup "$PYTHON_BIN" -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/api_hub.log" 2>&1 &
    echo "     API Hub avviato."
else
    echo "     API Hub già attivo."
fi

# Stage A: Text Ingester (Continua a girare per nuovi upload)
echo "  -> Avvio Stage A (Text Ingester)..."
nohup "$PYTHON_BIN" "$BASE_DIR/src/stages/stage_a_text_ingester.py" > "$LOG_DIR/stage_a.log" 2>&1 &

# Orchestratore Seriale (B -> C -> D)
PROJECT_ID=${1:-"Cronache-del-Silicio"}
echo "  -> Avvio Orchestratore Seriale per PROGETTO: $PROJECT_ID..."
nohup "$PYTHON_BIN" "$BASE_DIR/src/common/orchestrator.py" "$PROJECT_ID" > "$LOG_DIR/orchestrator.log" 2>&1 &

# Dashboard
echo "  -> Avvio Dashboard (Port 5173)..."
cd "$BASE_DIR/src/dashboard"
nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/dashboard.log" 2>&1 &
echo "     Dashboard avviata."
cd "$BASE_DIR"

echo "✅ Pipeline avviata in modalità SEQUENZIALE via Orchestrator."
echo "Controlla i log in $LOG_DIR/orchestrator.log per il progresso."
ps aux | grep -E "orchestrator|stage_a|uvicorn" | grep -v grep
