#!/usr/bin/env python3
"""
DIAS Project Reset Tool
Consente di resettare coerentemente lo stato di un progetto in Redis e nel config.json.
Ora gestisce anche lo spostamento automatico dei file fisici in sottocartelle di backup.
"""

import os
import sys
import json
import argparse
import shutil
from pathlib import Path

# Aggiungi la root del progetto al PYTHONPATH
sys.path.append(os.getcwd())

from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence

def main():
    parser = argparse.ArgumentParser(description="Reset project state in Redis and Config.")
    parser.add_argument("--project-id", required=True, help="ID normalizzato del progetto (es. urania_...)")
    parser.add_argument("--stage", required=True, choices=['b', 'c', 'd'], help="Stage da cui ripartire (pulisce se stesso e successivi)")
    parser.add_argument("--backup-name", help="Nome cartella di backup (es. backup_v2.2). Sposta i file prima del reset.")
    parser.add_argument("--dry-run", action="store_true", help="Simula le operazioni senza scrivere")
    
    args = parser.parse_args()
    
    project_id = DiasPersistence.normalize_id(args.project_id)
    redis = get_redis_client()
    persistence = DiasPersistence(project_id=project_id)
    
    if not persistence.project_root.exists():
        print(f"❌ Errore: Progetto {project_id} non trovato in data/projects/")
        sys.exit(1)

    # 1. Definiamo i parametri di reset in base allo stage target
    reset_configs = {
        'b': {
            'status': 'ready_for_semantic',
            'last_stage': 'stage_a',
            'checkpoint': 0,
            'registry_patterns': [r'chunk-\d{3}$', r'chunk-\d{3}-micro', r'scene-'],
            'stages_to_clear': ['stage_b', 'stage_c', 'stage_d']
        },
        'c': {
            'status': 'ready_for_scene',
            'last_stage': 'stage_b',
            'checkpoint': 1,
            'registry_patterns': [r'chunk-\d{3}-micro', r'scene-'],
            'stages_to_clear': ['stage_c', 'stage_d']
        },
        'd': {
            'status': 'ready_for_voice',
            'last_stage': 'stage_c',
            'checkpoint': 2,
            'registry_patterns': [r'scene-'],
            'stages_to_clear': ['stage_d']
        }
    }
    
    cfg = reset_configs[args.stage]
    
    print(f"--- 🔄 RESET PROGETTO: {project_id} ---")
    print(f"Target: Ripartenza da Stage {args.stage.upper()}")

    # 1.5 Backup File Fisici
    if args.backup_name:
        print(f"File System: Preparazione backup in '{args.backup_name}' per gli stage {cfg['stages_to_clear']}")
        for st_name in cfg['stages_to_clear']:
            out_dir = persistence.project_root / "stages" / st_name / "output"
            if out_dir.exists():
                backup_dir = out_dir / args.backup_name
                if not args.dry_run:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                
                moved_count = 0
                for f in out_dir.iterdir():
                    if f.is_file():
                        moved_count += 1
                        if not args.dry_run:
                            shutil.move(str(f), str(backup_dir / f.name))
                print(f"  - {st_name}: spostati {moved_count} file.")

    # 2. Pulizia Redis Registry (Hash fields)
    registry_key = f"dias:registry:{project_id}"
    all_fields = redis.client.hkeys(registry_key)
    fields_to_delete = []
    
    import re
    for field in all_fields:
        f_str = field.decode('utf-8') if isinstance(field, bytes) else field
        for pattern in cfg['registry_patterns']:
            if re.search(pattern, f_str):
                fields_to_delete.append(field)
                break
                
    print(f"Registry: Trovati {len(fields_to_delete)} task da rimuovere per Stage {args.stage}+")
    if not args.dry_run and fields_to_delete:
        redis.client.hdel(registry_key, *fields_to_delete)
        print("✅ Registry ripulito.")

    # 3. Pulizia Checkpoint
    checkpoint_key = f"dias:checkpoint:{project_id}"
    print(f"Checkpoint: Impostazione a {cfg['checkpoint']} (Stadio precedente completato)")
    if not args.dry_run:
        redis.client.set(checkpoint_key, cfg['checkpoint'])
        
    # 4. Reset Active Stage
    active_stage_key = f"dias:project:{project_id}:active_stage"
    print(f"Active Stage: Reset della chiave")
    if not args.dry_run:
        redis.client.delete(active_stage_key)
        
    # 5. Clear Global Pause (Safety)
    print("Security: Rimozione eventuale pausa globale")
    if not args.dry_run:
        redis.client.delete("dias:status:paused")

    # 6. Aggiornamento Config.json
    print(f"Config: Impostazione status='{cfg['status']}', last_stage='{cfg['last_stage']}'")
    if not args.dry_run:
        persistence.update_project_config({
            "status": cfg["status"],
            "last_stage": cfg["last_stage"]
        })
        print("✅ Config.json aggiornato.")
        
    if args.dry_run:
        print("\n⚠️ MODALITÀ DRY-RUN: Nessuna modifica effettuata.")
    else:
        print(f"\n✨ Reset completato con successo. Lo stato fisico e logico è pulito da Stage {args.stage.upper()}.")

if __name__ == "__main__":
    main()
