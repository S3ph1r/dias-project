#!/usr/bin/env python3
"""
Orchestratore Pipeline B2 — Sound-on-Demand v4.1

Esegue in sequenza:
  FASE 1 — B2-Macro: per ogni macro-chunk produce il MacroCue (PadRequest + PadArc)
  FASE 2 — B2-Micro: per ogni micro-chunk produce IntegratedCueSheet + SoundShoppingList
  FASE 3 — Aggregazione: unisce tutte le SoundShoppingList in
            `sound_shopping_list_aggregata.json` nella root del progetto.

La pipeline NON SI BLOCCA più sulla shopping list.
L'aggregato finale è l'input per Stage D2 (Sound Factory Client).

Flags:
  --cleanup     Cancella tutti gli output B2 esistenti prima di partire (fresh start).
  --macro-only  Esegue solo la Fase 1 (B2-Macro).
  --split       Usa architettura Director/Engineer (due chiamate per micro-chunk).
                Default: architettura monolitica (una chiamata per micro-chunk).
"""

import sys
import json
import time
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.persistence import DiasPersistence
from src.stages.stage_b2_macro import StageB2Macro
from src.stages.stage_b2_micro import StageB2Micro
from src.stages.stage_b2_micro_director import StageB2MicroDirector
from src.stages.stage_b2_micro_engineer import StageB2MicroEngineer


class B2PipelineOrchestrator:
    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.macro_worker = StageB2Macro(project_id)
        self.micro_worker = StageB2Micro(project_id)
        self.director_worker = StageB2MicroDirector(project_id)
        self.engineer_worker = StageB2MicroEngineer(project_id)
        self.b2_output_dir = (
            self.persistence.project_root / "stages" / "stage_b2" / "output"
        )
        self.b2_output_dir.mkdir(parents=True, exist_ok=True)
        self.trace_log = self.b2_output_dir / "b2_traceability.log"

    def log_session_marker(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sep = "=" * 60
        with open(self.trace_log, "a", encoding="utf-8") as f:
            f.write(f"\n{sep}\n[{ts}] [SESSION] {message}\n{sep}\n")

    def cleanup_b2_output(self):
        """Cancella tutti gli output B2 esistenti per un fresh start."""
        if self.b2_output_dir.exists():
            for f in self.b2_output_dir.iterdir():
                if f.is_file() and f.suffix == ".json":
                    f.unlink()
        print(f"🧹 Cleanup B2 output: {self.b2_output_dir}")

    def discover_chunks(self):
        """
        Scopre i macro-chunk e i loro micro-chunk dagli output di Stage B e Stage C.
        Ritorna: (chunk_ids, micro_map) dove micro_map[chunk_id] = [micro_ids]
        """
        stage_b_out = self.persistence.project_root / "stages" / "stage_b" / "output"
        stage_c_out = self.persistence.project_root / "stages" / "stage_c" / "output"

        chunk_ids = sorted([
            f.stem.split("-chunk-")[-1]
            for f in stage_b_out.glob(f"{self.project_id}-chunk-*.json")
            if "micro" not in f.stem
        ])

        micro_map: Dict[str, List[str]] = {}
        for chunk_id in chunk_ids:
            micro_ids = sorted([
                f.stem.split(f"-chunk-{chunk_id}-micro-")[-1].replace("-scenes", "")
                for f in stage_c_out.glob(f"{self.project_id}-chunk-{chunk_id}-micro-*-scenes.json")
            ])
            micro_map[chunk_id] = micro_ids

        return chunk_ids, micro_map

    def aggregate_shopping_lists(self) -> Dict:
        """
        Raccoglie tutti gli item SoundShopping da tutti i MicroCue e li aggrega.
        Deduplica per canonical_id (mantiene il primo occurrence, che include scene_id).
        Aggiunge anche il PAD di ogni MacroCue come item da produrre.
        Salva il risultato in `sound_shopping_list_aggregata.json`.
        """
        unique_assets: Dict[str, Dict] = {}

        # 1. Raccogli i PAD dai MacroCue (B2-Macro)
        for macro_file in sorted(self.b2_output_dir.glob("*-macro-cue.json")):
            try:
                with open(macro_file, "r", encoding="utf-8") as f:
                    macro_cue = json.load(f)
                pad = macro_cue.get("pad", {})
                cid = pad.get("canonical_id")
                if cid and cid not in unique_assets and not pad.get("is_leitmotif", False):
                    unique_assets[cid] = {
                        "type": "pad",
                        "canonical_id": cid,
                        "production_prompt": pad.get("production_prompt", ""),
                        "production_tags": pad.get("production_tags", ""),
                        "negative_prompt": pad.get("negative_prompt", ""),
                        "guidance_scale": pad.get("guidance_scale", 4.5),
                        "inference_steps": pad.get("inference_steps", 60),
                        "estimated_duration_s": pad.get("estimated_duration_s"),
                        "pad_arc": pad.get("pad_arc", []),
                        "scene_id": None,
                        "source": macro_file.name,
                    }
            except Exception as e:
                print(f"⚠️  Errore lettura MacroCue {macro_file.name}: {e}")

        # 2. Raccogli AMB/SFX/STING dalle MicroCue
        for micro_file in sorted(self.b2_output_dir.glob("*-micro-cue.json")):
            try:
                with open(micro_file, "r", encoding="utf-8") as f:
                    micro_cue = json.load(f)
                shopping_list = micro_cue.get("sound_shopping_list", [])
                for item in shopping_list:
                    cid = item.get("canonical_id")
                    if cid and cid not in unique_assets:
                        unique_assets[cid] = {
                            **item,
                            "source": micro_file.name,
                        }
            except Exception as e:
                print(f"⚠️  Errore lettura MicroCue {micro_file.name}: {e}")

        # 3. Salva aggregato
        aggregata = {
            "project_id": self.project_id,
            "generated_at": datetime.now().isoformat(),
            "total_assets": len(unique_assets),
            "assets_by_type": {
                "pad": len([a for a in unique_assets.values() if a["type"] == "pad"]),
                "amb": len([a for a in unique_assets.values() if a["type"] == "amb"]),
                "sfx": len([a for a in unique_assets.values() if a["type"] == "sfx"]),
                "sting": len([a for a in unique_assets.values() if a["type"] == "sting"]),
            },
            "assets": list(unique_assets.values()),
        }

        out_path = self.persistence.project_root / "sound_shopping_list_aggregata.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(aggregata, f, indent=2, ensure_ascii=False)

        return aggregata

    def run(self, cleanup: bool = False, macro_only: bool = False, split: bool = False):
        mode = "Director/Engineer" if split else "Monolitico"
        print(f"\n🚀 Avvio B2 Pipeline v4.1 ({mode}) — {self.project_id}")
        self.log_session_marker(f"START PIPELINE B2 v4.1 [{mode}] — {self.project_id}")

        if cleanup:
            self.cleanup_b2_output()

        chunk_ids, micro_map = self.discover_chunks()
        if not chunk_ids:
            print("❌ Nessun macro-chunk trovato. Verificare output Stage B.")
            sys.exit(1)

        print(f"📦 Trovati {len(chunk_ids)} macro-chunk: {chunk_ids}")

        # ── FASE 1: B2-Macro ───────────────────────────────────────
        print(f"\n{'─'*50}")
        print("🎼 FASE 1: MACRO-SPOTTER (Musical Director)")
        print(f"{'─'*50}")

        for chunk_id in chunk_ids:
            print(f"  ▶ Macro Chunk {chunk_id}...")
            ok = self.macro_worker.process_chunk(chunk_id)
            if not ok:
                print(f"❌ ERRORE FATALE: Macro Chunk {chunk_id} fallito. Pipeline interrotta.")
                sys.exit(1)
            print(f"  ✅ Macro Chunk {chunk_id} completato. Cooldown 60s...")
            time.sleep(60)

        if macro_only:
            print("\n⏸  Flag --macro-only: pipeline fermata dopo Fase 1.")
            return

        # ── FASE 2: B2-Micro (Monolitico o Director/Engineer) ──────
        print(f"\n{'─'*50}")
        if split:
            print("🎧 FASE 2: MICRO-SPOTTER (Director → Engineer)")
        else:
            print("🎧 FASE 2: MICRO-SPOTTER (Sound Designer)")
        print(f"{'─'*50}")

        for chunk_id in chunk_ids:
            micro_ids = micro_map.get(chunk_id, [])
            print(f"\n  Chunk {chunk_id}: {len(micro_ids)} micro-chunk")

            for micro_id in micro_ids:
                block_id = f"chunk-{chunk_id}-micro-{micro_id}"

                if split:
                    # ── Architettura Director/Engineer ──
                    print(f"  ▶ [Director] {block_id}...")
                    ok = self.director_worker.process(block_id)
                    if not ok:
                        print(f"❌ ERRORE FATALE: Director {block_id} fallito. Pipeline interrotta.")
                        sys.exit(1)
                    print(f"  ✅ [Director] {block_id} completato. Cooldown 60s...")
                    time.sleep(60)

                    print(f"  ▶ [Engineer] {block_id}...")
                    ok = self.engineer_worker.process(block_id)
                    if not ok:
                        print(f"❌ ERRORE FATALE: Engineer {block_id} fallito. Pipeline interrotta.")
                        sys.exit(1)
                    print(f"  ✅ [Engineer] {block_id} completato. Cooldown 60s...")
                    time.sleep(60)

                else:
                    # ── Architettura Monolitica (default) ──
                    print(f"  ▶ {block_id}...")
                    ok = self.micro_worker.process_micro_chunk(block_id)
                    if not ok:
                        print(f"❌ ERRORE FATALE: {block_id} fallito. Pipeline interrotta.")
                        sys.exit(1)
                    print(f"  ✅ {block_id} completato. Cooldown 60s...")
                    time.sleep(60)

        # ── FASE 3: Aggregazione ───────────────────────────────────
        print(f"\n{'─'*50}")
        print("📋 FASE 3: AGGREGAZIONE SOUND SHOPPING LIST")
        print(f"{'─'*50}")

        aggregata = self.aggregate_shopping_lists()
        total = aggregata["total_assets"]
        by_type = aggregata["assets_by_type"]
        out_path = self.persistence.project_root / "sound_shopping_list_aggregata.json"

        print(f"\n✅ Sound Shopping List Aggregata:")
        print(f"   Totale asset unici da produrre: {total}")
        print(f"   → PAD: {by_type['pad']} | AMB: {by_type['amb']} | SFX: {by_type['sfx']} | STING: {by_type['sting']}")
        print(f"   Salvata in: {out_path}")
        print(f"\n👉 Prossimo step: eseguire Stage D2 con questo file come input.")

        self.log_session_marker(
            f"END PIPELINE B2 v4.1 — {total} asset da produrre → Stage D2"
        )


def main():
    parser = argparse.ArgumentParser(description="DIAS B2 Pipeline v4.1 — Sound-on-Demand")
    parser.add_argument("project_id", help="ID del progetto")
    parser.add_argument("--cleanup", action="store_true", help="Cancella output B2 esistenti")
    parser.add_argument("--macro-only", action="store_true", help="Esegui solo B2-Macro")
    parser.add_argument("--split", action="store_true",
                        help="Usa architettura Director/Engineer (2 chiamate per micro-chunk)")
    args = parser.parse_args()

    orchestrator = B2PipelineOrchestrator(args.project_id)
    orchestrator.run(cleanup=args.cleanup, macro_only=args.macro_only, split=args.split)


if __name__ == "__main__":
    main()
