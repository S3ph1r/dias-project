# DIAS Documentation Index (v7.0)

DIAS (Distributed Immersive Audiobook System) — pipeline Python per produrre audiobook teatrali di qualità cinematografica (benchmark: BBC Radio Drama anni '80, Star Wars Audio Drama NPR 1981).

---

## Architettura e Strategia

- **[Master Blueprint v7.0](./blueprint.md)**: Pipeline completa (Stage 0-E), Stage B2 Sound-on-Demand v4.1, architettura Director/Engineer, modelli dati chiave.
- **[Workflow Logic v10.0](./dias-workflow-logic.md)**: Flusso dati tra stage, modalità B2 (monolitica vs --split), regole AMB/SFX/STING quantitative, flag CLI.
- **[Technical Reference](./technical-reference.md)**: Deployment, SOPS/Age, Redis internals, schemi JSON completi, vocabolario Qwen3, PAD arc rules.

---

## Produzione e Sound Design

- **[Production Standard v3.0](./production-standard.md)**: Formula Oscar (voce), paradigma BBC/Star Wars (sound design), regole quantitative AMB/SFX/STING, ducking depth, fade speed.
- **[DIAS-ARIA Integration v3.0](./dias-aria-integration-master.md)**: Contratto tecnico DIAS-ARIA: ACE-Step (unico modello), queue Redis, timing, HTDemucs stem separation, vocabolario Qwen3.
- **[Pre-production Guide](./preproduction-guide.md)**: Stage 0, Casting, Dashboard, `preproduction.json`.

---

## Inventario e Storia

- **[Component Inventory v2.0](./dias-inventory.md)**: Inventario tecnico completo: file Python, prompt YAML con versioni, modelli Pydantic, dipendenze.
- **[Prompt Evolution](./prompt-evolution.md)**: Storia versioni prompt Stage 0, B, B2 (Macro/Micro/Director/Engineer), C. Lezioni apprese.

---

## Quickstart

### Prerequisiti
```bash
pip install -r requirements.txt   # Python >= 3.10
# Variabili d'ambiente
cp .env.example .env
# MOCK_SERVICES=true per sviluppo offline
```

### Esecuzione Pipeline B2

```bash
# Modalità monolitica (default — una chiamata LLM per micro-chunk)
python tests/stages/run_b2_pipeline.py <project_id>

# Modalità split Director/Engineer (due chiamate LLM per micro-chunk)
python tests/stages/run_b2_pipeline.py <project_id> --split

# Solo B2-Macro (produce MacroCue + PadArc, salta B2-Micro)
python tests/stages/run_b2_pipeline.py <project_id> --macro-only

# Fresh start (cancella output B2 esistenti prima di partire)
python tests/stages/run_b2_pipeline.py <project_id> --cleanup

# Combinazioni
python tests/stages/run_b2_pipeline.py <project_id> --cleanup --split
```

### Struttura Directory

```
dias/
├── src/
│   ├── common/          # Fondamenta: config, models, gateway, persistence, registry
│   └── stages/
│       ├── stage_0_intel.py
│       ├── stage_a_text_ingester.py
│       ├── stage_b_semantic_analyzer.py
│       ├── stage_b2_macro.py           # Musical Director
│       ├── stage_b2_micro.py           # Sound Designer (monolitico, legacy)
│       ├── stage_b2_micro_director.py  # Narrative Event Extractor (split v1.0)
│       ├── stage_b2_micro_engineer.py  # ACE-Step Spec Generator (split v1.0)
│       ├── stage_c_scene_director.py
│       ├── stage_d_voice_gen.py
│       └── stage_d2_sound_factory.py
├── config/
│   └── prompts/
│       ├── stage_0/
│       ├── stage_b/
│       ├── stage_b2/    # b2_macro_v4.0.yaml, b2_micro_v4.0.yaml,
│       │                #  b2_micro_director_v1.0.yaml, b2_micro_engineer_v1.0.yaml
│       └── stage_c/
├── tests/
│   └── stages/
│       └── run_b2_pipeline.py          # Orchestratore pipeline B2
└── docs/
    ├── README.md                        # questo file
    ├── blueprint.md
    ├── dias-workflow-logic.md
    ├── technical-reference.md
    ├── production-standard.md
    ├── dias-aria-integration-master.md
    ├── preproduction-guide.md
    ├── dias-inventory.md
    ├── prompt-evolution.md
    └── archive/                         # doc obsoleti con nota di deprecazione
```

---

## Archivio Storico

Documenti obsoleti conservati in `docs/archive/` con nota di deprecazione in testa:

| File | Motivo archiviazione |
| :--- | :--- |
| `sound-library-blueprint.md` | Descrive il vecchio sistema Warehouse-First con Redis catalog e sound library. Sostituito da Sound-on-Demand v4.1. |
| `ROADMAP_SOUND_CREATION_MIX.md` | Descrive il workflow B2 con stop-on-missing e Redis catalog. Architettura superseded. |
| `dias-component-inventory.md` | Versione precedente dell'inventario (v1.0). |
| `dias-workflow-logic.md` (archivio) | Versione v9.0 pre-Director/Engineer. |
| Altri file in `archive/` | Versioni precedenti di blueprint, dashboard, guide. |
