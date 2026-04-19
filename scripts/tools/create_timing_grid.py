#!/usr/bin/env python3
"""
DIAS Master Timing Grid Generator
---------------------------------
Aggrega gli output dello Stage D per creare una timeline assoluta del progetto.
Fondamentale per la sincronizzazione sonora dello Stage B2 ed E.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone

# Aggiunge la root del progetto al path per importare i moduli common
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.common.persistence import DiasPersistence, DateTimeEncoder
from src.common.models import MasterTimingGrid, TimingMacroChunk, TimingMicroChunk, TimingScene

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("timing-grid-gen")

def parse_scene_id(scene_id: str):
    """
    Estrae macro, micro e scene index da un ID scena standard.
    Esempio: chunk-000-micro-001-scene-005 -> (chunk-000, chunk-000-micro-001, 5)
    """
    parts = scene_id.split("-")
    # parts: ['chunk', '000', 'micro', '001', 'scene', '005']
    macro_id = f"{parts[0]}-{parts[1]}"
    micro_id = f"{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}"
    scene_idx = int(parts[5])
    return macro_id, micro_id, scene_idx

def generate_grid(project_id: str):
    logger.info(f"🚀 Generazione Master Timing Grid per il progetto: {project_id}")
    
    persistence = DiasPersistence(project_id=project_id)
    stage_d_out = persistence.project_root / "stages" / "stage_d" / "output"
    
    if not stage_d_out.exists():
        logger.error(f"❌ Directory di output Stage D non trovata: {stage_d_out}")
        return

    # 1. Scansione e caricamento dati
    json_files = list(stage_d_out.glob("*-scene-*.json"))
    if not json_files:
        logger.warning(f"⚠️ Nessun file JSON di scena trovato in {stage_d_out}")
        return

    logger.info(f"📂 Trovati {len(json_files)} file di scena.")

    all_scenes_data = []
    for f in json_files:
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                data = json.load(jf)
                # Verifica che i campi necessari esistano
                if "scene_id" in data and "voice_duration_seconds" in data:
                    all_scenes_data.append(data)
        except Exception as e:
            logger.error(f"❌ Errore lettura {f}: {e}")

    # 2. Ordinamento (Macro -> Micro -> Scene Index)
    def sort_key(data):
        macro, micro, idx = parse_scene_id(data["scene_id"])
        return (macro, micro, idx)

    all_scenes_data.sort(key=sort_key)

    # 3. Elaborazione Timeline
    total_time = 0.0
    macro_chunks: Dict[str, TimingMacroChunk] = {}

    for data in all_scenes_data:
        scene_id = data["scene_id"]
        voice_dur = float(data.get("voice_duration_seconds", 0.0))
        pause_ms = float(data.get("pause_after_ms", 0.0))
        pause_sec = pause_ms / 1000.0
        speaker = data.get("speaker")
        
        macro_id, micro_id, _ = parse_scene_id(scene_id)
        
        # Inizializza Macro se non esiste
        if macro_id not in macro_chunks:
            macro_chunks[macro_id] = TimingMacroChunk(
                macro_chunk_id=macro_id,
                start_offset=total_time,
                duration=0.0,
                micro_chunks={}
            )
            
        macro = macro_chunks[macro_id]
        
        # Inizializza Micro se non esiste
        if micro_id not in macro.micro_chunks:
            macro.micro_chunks[micro_id] = TimingMicroChunk(
                micro_chunk_id=micro_id,
                start_offset=total_time,
                duration=0.0,
                scenes=[]
            )
            
        micro = macro.micro_chunks[micro_id]
        
        # Crea la TimingScene
        timing_scene = TimingScene(
            scene_id=scene_id,
            start_offset=total_time,
            voice_duration=voice_dur,
            pause_after=pause_sec,
            total_scene_time=voice_dur + pause_sec,
            speaker=speaker
        )
        
        # Aggiorna accumulatori
        micro.scenes.append(timing_scene)
        micro.duration += timing_scene.total_scene_time
        macro.duration += timing_scene.total_scene_time
        total_time += timing_scene.total_scene_time

    # 4. Creazione Grid Finale
    grid = MasterTimingGrid(
        project_id=project_id,
        total_duration_seconds=total_time,
        macro_chunks=macro_chunks
    )

    # 5. Salvataggio
    output_path = persistence.project_root / "stages" / "stage_d" / "master_timing_grid.json"
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # Usiamo il metodo dict() di Pydantic per la serializzazione
            json.dump(grid.model_dump(), f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
        
        logger.info(f"✅ Master Timing Grid generata con successo: {output_path}")
        logger.info(f"⏱️ Durata totale stimata: {total_time:.2f} secondi (~{total_time/60:.2f} minuti)")
        
    except Exception as e:
        logger.error(f"❌ Errore durante il salvataggio della griglia: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera la Master Timing Grid di un progetto DIAS.")
    parser.add_argument("project_id", help="ID del progetto (es. urania_n_1610...)")
    
    args = parser.parse_args()
    generate_grid(args.project_id)
