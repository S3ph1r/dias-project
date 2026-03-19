#!/bin/bash
# stop_pipeline.sh - Arresto controllato della pipeline DIAS

echo "🛑 Arresto della pipeline DIAS in corso..."

# Kill dei worker Python (Stage A, B, C e orchestratori)
pkill -f "orchestrator.py"
pkill -f "stage_"
pkill -f "python3 -c"
pkill -f "start_pipeline.sh"
pkill -f "vite"
pkill -f "svelte-kit"

# Verifica
sleep 2
COUNT=$(pgrep -f "orchestrator.py|stage_")

if [ -z "$COUNT" ]; then
    echo "✅ Tutti i processi della pipeline sono stati terminati."
else
    echo "⚠️ Alcuni processi sono ancora attivi. Forza arresto..."
    pkill -9 -f "orchestrator.py"
    pkill -9 -f "stage_"
    pkill -9 -f "python3 -c"
    echo "💀 Forza arresto completato."
fi
