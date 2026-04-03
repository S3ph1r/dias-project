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

# --- AMBIENTE ---
# (Rimosso vecchio blocco di sicurezza per permettere check idempotenti)

# --- COMPONENTS ---

# 1. API Hub (Port 8000)
echo "  -> Verifica API Hub (Port 8000)..."
if pgrep -f "src.api.main:app" > /dev/null; then
    echo "     ✅ API Hub già attivo."
else
    echo "     🚀 Avvio API Hub..."
    nohup "$PYTHON_BIN" -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/api_hub.log" 2>&1 &
    sleep 2
fi

# 2. Stage A: Text Ingester
echo "  -> Verifica Stage A (Text Ingester)..."
if pgrep -f "stage_a_text_ingester.py" > /dev/null; then
    echo "     ✅ Stage A già attivo."
else
    echo "     🚀 Avvio Stage A..."
    nohup "$PYTHON_BIN" "$BASE_DIR/src/stages/stage_a_text_ingester.py" > "$LOG_DIR/stage_a.log" 2>&1 &
fi

# 3. Stage D: Voice Generator (Proxy)
echo "  -> Verifica Stage D (Voice Generator)..."
if pgrep -f "stage_d_voice_gen.py" > /dev/null; then
    echo "     ✅ Stage D già attivo."
else
    echo "     🚀 Avvio Stage D..."
    nohup "$PYTHON_BIN" "$BASE_DIR/src/stages/stage_d_voice_gen.py" > "$LOG_DIR/stage_d.log" 2>&1 &
fi

# 4. Orchestratore Seriale (Macro-Logic)
PROJECT_ID=${1:-"Cronache-del-Silicio"}
echo "  -> Verifica Orchestratore per PROGETTO: $PROJECT_ID..."
if pgrep -f "src/common/orchestrator.py.*$PROJECT_ID" > /dev/null; then
    echo "     ✅ Orchestratore per $PROJECT_ID già attivo."
else
    echo "     🚀 Avvio Orchestratore per $PROJECT_ID..."
    nohup "$PYTHON_BIN" "$BASE_DIR/src/common/orchestrator.py" "$PROJECT_ID" > "$LOG_DIR/orchestrator.log" 2>&1 &
fi

# 5. Dashboard (Port 5173)
echo "  -> Verifica Dashboard (Port 5173)..."
if pgrep -f "vite" > /dev/null || pgrep -f "svelte-kit" > /dev/null; then
    echo "     ✅ Dashboard già attiva."
else
    echo "     🚀 Avvio Dashboard..."
    cd "$BASE_DIR/src/dashboard" || exit
    nohup npm run dev -- --host 0.0.0.0 > "$LOG_DIR/dashboard.log" 2>&1 &
    cd "$BASE_DIR" || exit
fi

echo ""
echo "✨ Pipeline DIAS pronta."
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "🔗 Dashboard: http://$IP_ADDR:5173"
echo "🔗 API Hub:   http://$IP_ADDR:8000/docs"
echo ""
echo "Usa ./stop_pipeline.sh per fermare tutto."
