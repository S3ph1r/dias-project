# ARIA Sound Library: Il Metodo Semantico Universale
## Revisione v1.2 — Aprile 2026

Questo documento è il Manuale di Governo della Sound Library di **ARIA**. Definisce le regole auree per popolare il magazzino audio e funge da **API Concettuale** per i sistemi esterni (es. **DIAS**).

---

## 1. Lo Scopo del Metodo (Anti-Proliferazione)

Il principio fondante è il **Riuso Universale**. È vietato generare suoni legati a un'opera specifica. I suoni devono essere legati a **Archetipi Emotivi Umani**.

---

## 2. Il "Kit Cinematico" (Unità Primitiva Audio)

ARIA produce per **Kit Scomponibili**:
*   **Pad (Stem A)**: Tappeti atmosferici asettici per loop infiniti.
*   **Stings (Stem C)**: Colpi, shock, sfx brevi (3-10s) per pause drammatiche.

---

## 3. L'Interfaccia Semantica (Redis Discovery)

### Il Paradigma "Reading Comprehension"
Le macchine client non fanno ricerche matematiche, ma "leggono" i metadati. Ogni asset in `data/assets/` deve avere un `profile.json`:

```json
{
  "id": "pad_scifi_dread_01",
  "category": "pad",
  "tags": ["sci-fi", "thriller", "dark", "tension"],
  "semantic_description": "Frequenze basse pulsanti lente. Senso del tempo che scade."
}
```

### La Meccanica del Pescaggio
1. **Pubblicazione (ARIA)**: L'`AriaRegistryManager` scansiona il magazzino e pubblica su Redis la chiave `aria:registry:master` (Host: `{ARIA_NODE_IP}`, attualmente `192.168.1.139`).
2. **Consultazione (Client)**: L'App esterna (Stage B2 di DIAS) carica questo JSON e cerca un'aderenza semantica tra la scena e i `tags`.

---

## 4. L'Evoluzione del Catalogo: Il Pattern "Shopping List"

Quando un client ha bisogno di suoni non presenti a magazzino, si innesca il ciclo produttivo:

1. **Scan e Accumulo**: Il Client (DIAS) processa il libro. Se un asset manca, lo segna nella `shopping_list.json`.
2. **Industrial Batch Run**: L'operatore in ARIA usa la lista per redigere un `production_order.csv`.
3. **Fabbrica (Sound Factory)**: `python scripts/sound_factory.py --batches order.csv`.
4. **Auto-Discovery**: Al termine della generazione, il nuovo asset viene salvato in `data/assets/`. Al riavvio del nodo ARIA, il `RegistryManager` lo pubblica automaticamente nel Master Registry.

---
*Status: Documento Architetturale ARIA v1.2*
