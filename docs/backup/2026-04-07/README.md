# 📚 DIAS Documentation Index (v6.8)

Benvenuto nella documentazione di DIAS (Distributed Immersive Audiobook System).  
Questa guida ti aiuta a navigare tra i diversi componenti e le specifiche del sistema.

---

## 🏗️ Core Architecture & Strategy
- **[Master Blueprint v6.8](./blueprint.md)**: Il documento "Omnibus". Contiene la visione, la pipeline a 9 stadi, i pattern di resilienza e i rischi identificati. **(GONFIO & COMPLETO)**.
- **[Technical Reference](./technical-reference.md)**: Specifiche di basso livello: Deployment, Security (SOPS/Age), Redis Internals e Metriche di successo.
- **[Component Inventory](./dias-component-inventory.md)**: Indice tecnico di classi, funzioni e dipendenze.

---

## 🎬 Pre-production & Production
- **[Pre-production Guide](./preproduction-guide.md)**: Manuale operativo per lo **Stage 0**, il casting, il sound design e la gestione dei libri lunghi.
- **[Workflow Status Board](./dias_workflow_status.md)**: Quadro aggiornato dello stato di implementazione reale vs design.

---

## 📂 Archivio Storico
I documenti originali e i roadmap storici sono conservati per consultazione nella cartella:
👉 **[archive/](./archive/)**

- `development-roadmap.md` (Legacy Roadmap)
- `master_registry_design.md` (Design originale)
- `dias_aria_decoupling.md` (Design originale)
- `sops_age_integration.md` (Specifica sicurezza)

---

## 📦 Python Quickstart
Il sistema richiede un ambiente Python ≥ 3.10.
👉 **[requirements.txt](../requirements.txt)**

```bash
pip install -r requirements.txt
```
