#!/usr/bin/env python3
"""
Test/Orchestrator dedicato esclusivamente agli Stage B2 (Macro e Micro).
Esegue B2-Macro su tutto il progetto. Ferma tutto se mancano asset.
Poi esegue B2-Micro. Ferma tutto se mancano asset.
Supporta l'idempotenza: non cancella i file esistenti se non richiesto.
"""

import os
import sys
import json
import glob
import time
from pathlib import Path
from datetime import datetime

# Aggiungi il path root al Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.stages.stage_b2_macro import StageB2Macro
from src.stages.stage_b2_micro import StageB2Micro
from src.common.persistence import DiasPersistence

class B2Orchestrator:
    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.macro_worker = StageB2Macro(self.project_id)
        self.micro_worker = StageB2Micro(self.project_id)

    def cleanup_b2_output(self):
        """Pulisce la cartella di output di B2 prima di una nuova esecuzione."""
        b2_out = self.persistence.project_root / "stages" / "stage_b2" / "output"
        if b2_out.exists():
            print(f"🧹 Pulizia totale output B2: {b2_out}")
            for f in b2_out.glob("*.json"):
                f.unlink()

    def _get_project_chunks(self) -> list:
        """Restituisce la lista dei `chunk_id` disponibili dallo Stage B."""
        b_out = self.persistence.project_root / "stages" / "stage_b" / "output"
        if not b_out.exists():
            return []
        
        files = glob.glob(f"{b_out}/{self.project_id}-chunk-[0-9][0-9][0-9].json")
        chunks = []
        for file in files:
            name = Path(file).name
            chunk_id = name.split("-chunk-")[1].replace(".json", "")
            chunks.append(chunk_id)
        return sorted(chunks)

    def _get_micro_chunks_for_chunk(self, chunk_id: str) -> list:
        """Restituisce la lista dei micro-chunk disponibili per un dato chunk dallo Stage C."""
        c_out = self.persistence.project_root / "stages" / "stage_c" / "output"
        if not c_out.exists():
            return []
        
        prefix = f"{self.project_id}-chunk-{chunk_id}-micro-"
        files = glob.glob(f"{c_out}/{prefix}[0-9][0-9][0-9]-scenes.json")
        micros = []
        for file in files:
            name = Path(file).name
            micro_id = name.split("-micro-")[1].replace("-scenes.json", "")
            micros.append(micro_id)
        return sorted(micros)

    def aggregate_shopping_lists(self) -> bool:
        """
        Aggrega tutte le shopping list prodotte (macro e micro) in un unico file master.
        Ritorna True se sono state trovate mancanze.
        """
        b2_out = self.persistence.project_root / "stages" / "stage_b2" / "output"
        if not b2_out.exists():
            return False

        files = glob.glob(f"{b2_out}/*-shopping-list-*.json")
        master_list = []
        
        for file in files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    items = data.get("missing_assets", [])
                    master_list.extend(items)
            except Exception as e:
                print(f"⚠️ Errore lettura shopping list {file}: {e}")
        
        if master_list:
            # Rimuoviamo duplicati basandoci sul canonical_id (nuovo standard V3)
            # Se manca canonical_id, usiamo il production_prompt o universal_prompt come fallback
            unique_items = {}
            for item in master_list:
                key = item.get("canonical_id") or item.get("production_prompt") or item.get("universal_prompt")
                if key not in unique_items:
                    unique_items[key] = item
            
            master_file = self.persistence.project_root / f"master_shopping_list_{self.project_id}.json"
            legacy_file = self.persistence.project_root / "master_shopping_list_micro.json"
            
            output_data = {
                "project_id": self.project_id,
                "generated_at": datetime.now().isoformat(),
                "total_missing_unique": len(unique_items),
                "missing_assets": list(unique_items.values())
            }
            
            for path in [master_file, legacy_file]:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n❌ [STOP-ON-MISSING] {len(unique_items)} asset mancanti unici rilevati.")
            print(f"Master Shopping List salvata in: {master_file}")
            print(f"Copia compatibilità creata: {legacy_file}")
            return True
        
        return False

    def log_session_marker(self, marker: str):
        """Scrive un marker di sessione nel log di tracciabilità."""
        log_path = self.persistence.project_root / "stages" / "stage_b2" / "output" / "b2_traceability.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[{timestamp}] [SESSION] {marker}\n{'='*60}\n")

    def run(self, force_cleanup=False):
        chunks = self._get_project_chunks()
        if not chunks:
            print("Nessun chunk trovato. Hai eseguito Stage B?")
            return

        print(f"🚀 Avvio B2 Pipeline (Integrated) per {self.project_id}")
        
        if force_cleanup:
            self.cleanup_b2_output()
            
        self.log_session_marker(f"START PIPELINE B2 - Project: {self.project_id}")
        
        # --- FASE 1: MACRO ---
        print("\n=== FASE 1: MACRO-SPOTTER (Pad Palette) ===")
        for chunk_id in chunks:
            print(f"Lavorando su Macro Chunk {chunk_id}...")
            success = self.macro_worker.process_chunk(chunk_id)
            if not success:
                print(f"❌ ERRORE FATALE Macro Chunk {chunk_id} fallito dopo i tentativi. Interruzione di sicurezza.")
                sys.exit(1)
            print("⏳ Cooldown post-macro (60s)...")
            time.sleep(60)

        # --- FASE 2: MICRO ---
        print("\n=== FASE 2: MICRO-SPOTTER (Integrated Cue Sheet) ===")
        for chunk_id in chunks:
            micros = self._get_micro_chunks_for_chunk(chunk_id)
            print(f"Chunk {chunk_id}: elaborazione {len(micros)} micro-chunks...")
            for micro_id in micros:
                print(f"Lavorando su Micro Chunk {chunk_id}-{micro_id}...")
                success = self.micro_worker.process_micro(chunk_id, micro_id)
                if not success:
                    print(f"❌ ERRORE FATALE Micro Chunk {chunk_id}-{micro_id} fallito dopo i tentativi. Interruzione di sicurezza.")
                    sys.exit(1)
                print("⏳ Cooldown inter-micro (60s)...")
                time.sleep(60)

        # 3. Final Check & Aggregation
        has_missing = self.aggregate_shopping_lists()
        
        if has_missing:
            print("\n⚠️ PIPELINE BLOCCATA: Produrre gli asset mancanti (ARIA PC 139) prima di procedere allo Stage E.")
            self.log_session_marker("STOP PIPELINE B2 - Pending Shopping List")
            sys.exit(1)

        print("\n✅ PIPELINE B2 COMPLETATA CON SUCCESSO! ✅")
        self.log_session_marker("END PIPELINE B2 - Success")
        print("Il copione artistico integrato è pronto per lo Stage E synthesis.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_b2_pipeline.py <project_name> [--cleanup]")
        sys.exit(1)
        
    project_id = sys.argv[1]
    cleanup = "--cleanup" in sys.argv
    
    orchestrator = B2Orchestrator(project_id)
    orchestrator.run(force_cleanup=cleanup)
