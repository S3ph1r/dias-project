#!/bin/bash
# start_voice.sh
# Avvia il worker dello Stage D (Voice Generation) in background.

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$BASE_DIR/.venv/bin/python3"
export PYTHONPATH="$BASE_DIR"

echo "🎙️ Avvio Worker STAGE D (Voice Generation)..."
echo "Log: logs/stage_d.log"
echo ""

nohup "$PYTHON_BIN" "$BASE_DIR/src/stages/stage_d_voice_gen.py" > "$BASE_DIR/logs/stage_d.log" 2>&1 &

echo "✅ Worker avviato. Monitora logs/stage_d.log per il progresso."
