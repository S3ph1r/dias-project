#!/bin/bash
# start_regia.sh
# Esegue la pipeline fino allo Stage C (Regia) e poi si ferma per intervento manuale.

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$BASE_DIR/.venv/bin/python3"
export PYTHONPATH="$BASE_DIR"

PROJECT_ID=${1:-"Cronache-del-Silicio"}

echo "🎭 Avvio Pipeline fino alla REGIA (Stage B + C) per: $PROJECT_ID"
echo "Al termine, potrai selezionare la voce in Dashboard e premere Resume."
echo ""

"$PYTHON_BIN" "$BASE_DIR/src/common/orchestrator.py" "$PROJECT_ID" --limit-stage stage_c

echo ""
echo "✅ Regia completata. Ora procedi dalla Dashboard:"
echo "1. Seleziona 'eleven'"
echo "2. Premi 'Resume Pipeline'"
