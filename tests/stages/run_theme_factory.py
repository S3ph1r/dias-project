#!/usr/bin/env python3
"""
Runner Stage 0.5 — Theme Factory

Genera i profili musicali (leitmotif) per i personaggi principali del progetto.
Chiama Gemini per ogni personaggio e scrive project_sound_palette in preproduction.json.
NON produce WAV — la produzione ARIA è responsabilità di Stage D2.

Flags:
  --no-secondary   Genera solo personaggi primary (default: primary + secondary)
  --force          Rigenera anche se project_sound_palette esiste già
  --dry-run        Mostra i personaggi selezionati senza chiamare Gemini
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.persistence import DiasPersistence
from src.stages.stage_0_5_theme_factory import Stage05ThemeFactory


def dry_run(project_id: str, include_secondary: bool) -> None:
    pid = DiasPersistence.normalize_id(project_id)
    persistence = DiasPersistence(project_id=pid)
    preprod_path = persistence.get_preproduction_path()

    if not preprod_path or not preprod_path.exists():
        print(f"❌ preproduction.json non trovato: {preprod_path}")
        sys.exit(1)

    with open(preprod_path, encoding="utf-8") as f:
        preprod = json.load(f)

    palette = preprod.get("palette_choice", "N/A")
    characters = preprod.get("characters_dossier", [])
    roles = {"primary"} | ({"secondary"} if include_secondary else set())
    selected = [c for c in characters if c.get("role_category") in roles]

    print(f"\n🔍 Dry-run — {pid}")
    print(f"   Palette: {palette}")
    print(f"   Personaggi selezionati ({len(selected)}):")
    for c in selected:
        print(f"     [{c.get('role_category','?'):10s}] {c.get('name')} — {c.get('role_description','')}")

    existing = preprod.get("project_sound_palette", {})
    if existing:
        print(f"\n   ⚠  project_sound_palette già presente ({len(existing)} temi):")
        for cid in existing:
            print(f"     {cid}")
        print("   Usa --force per rigenerare.")
    else:
        print(f"\n   project_sound_palette: non presente — verrà creato")

    print(f"\n   Gemini calls necessarie: {len(selected)}")
    print(f"   Tempo stimato: ~{len(selected) * 5}s")


def main():
    parser = argparse.ArgumentParser(
        description="DIAS Stage 0.5 — Theme Factory (profili leitmotif, solo LLM)"
    )
    parser.add_argument("project_id",     help="ID del progetto")
    parser.add_argument("--no-secondary", action="store_true",
                        help="Solo personaggi primary (default: primary + secondary)")
    parser.add_argument("--force",        action="store_true",
                        help="Rigenera anche se project_sound_palette già presente")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Mostra personaggi selezionati senza chiamare Gemini")
    args = parser.parse_args()

    include_secondary = not args.no_secondary

    if args.dry_run:
        dry_run(args.project_id, include_secondary)
        return

    print(f"\n🎼 Stage 0.5 Theme Factory")
    print(f"   Progetto  : {args.project_id}")
    print(f"   Personaggi: primary{'+ secondary' if include_secondary else ' only'}")
    print(f"   Force     : {'sì' if args.force else 'no (skip se già presente)'}")
    print()

    t0 = datetime.now()
    stage = Stage05ThemeFactory(args.project_id, include_secondary=include_secondary)
    ok = stage.run(force=args.force)
    elapsed = (datetime.now() - t0).total_seconds()

    if ok:
        persistence = DiasPersistence(project_id=DiasPersistence.normalize_id(args.project_id))
        preprod_path = persistence.get_preproduction_path()
        with open(preprod_path, encoding="utf-8") as f:
            preprod = json.load(f)
        palette = preprod.get("project_sound_palette", {})

        print(f"\n{'─'*60}")
        print(f"✅ Completato in {elapsed:.1f}s — {len(palette)} leitmotif")
        print(f"{'─'*60}")
        for cid, entry in palette.items():
            print(f"\n  🎵 {cid}")
            print(f"     Personaggio: {entry['character_name']} [{entry['role_category']}]")
            print(f"     Profilo    : {entry['musical_profile'][:100]}...")
            print(f"     Prompt     : {entry['generation_prompt'][:100]}...")
            print(f"     Durata     : {entry['duration_s']}s | Seed: {entry['seed']}")

        print(f"\n👉 Prossimo step: Stage D2 includerà i leitmotif base nella shopping list ARIA.")
    else:
        print(f"\n❌ Stage 0.5 fallito dopo {elapsed:.1f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
