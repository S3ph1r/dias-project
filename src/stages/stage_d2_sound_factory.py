#!/usr/bin/env python3
"""
Stage D2 — Sound Factory Client v4.2 (ACE-Step 1.5 XL / ARIA Wrapper v2.0)

Questo stage consuma la 'sound_shopping_list_aggregata.json' e:
1. Deduplica gli asset per canonical_id.
2. Per ogni asset, costruisce un payload compatibile con il connettore ARIA ACEStepBackend.
3. Invia la richiesta ad ARIA (PC 139) via Redis su aria:q:mus:local:acestep-1.5-xl-sft:dias.
4. Attende il callback su aria:c:dias:{job_id}.
5. Scarica master WAV + stem WAV (bass/drums/other) da ARIA HTTP (porta 8082).
6. Genera un 'manifest.json' che mappa ogni canonical_id ai file fisici locali.

Protocollo ARIA (DIAS e ARIA sono agnostici, parlano solo via Redis su LXC 120):
  - DIAS spedisce task in coda; ARIA esegue relay + HTDemucs (GPU) e risponde via callback.
  - Il vocabolario dei prompt è già in formato ACE-Step nativo (gestito dal prompt B2-Macro v4.2).
  - Coda Task:  aria:q:mus:local:acestep-1.5-xl-sft:dias
  - Callback:   aria:c:dias:{job_id}
  - Formato callback ARIA: {"status": "done", "output": {"audio_url": ..., "stems": {...}}}
"""

import hashlib
import json
import sys
import time
import requests
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.logging_setup import get_logger


# Stem names produced by ARIA HTDemucs (GPU, lato ARIA).
# "vocals" escluso: PAD è sempre strumentale, la traccia vocals sarebbe silenzio/residuo.
DEMUCS_STEMS = ["bass", "drums", "other"]

# Intensity → ACE-Step structural tag (per costruzione lyrics dal pad_arc)
_INTENSITY_TO_TAG = {
    "low":  None,        # resolved by position (first→Intro, last→Outro)
    "mid":  "[Verse]",
    "high": "[Chorus]",
}

# Prefisso funzionale fisso — garantisce che il ruolo del PAD sia sempre presente
# indipendentemente da quanto B2-Macro abbia già incluso nei production_tags.
_PROMPT_PREFIX = "cinematic underscore, no vocals, instrumental, "


class StageD2SoundFactory:
    """
    Sound Factory Client — Consuma la shopping list di B2 e produce
    asset audio tramite ARIA ACE-Step 1.5 XL (wrapper v2.0).

    Protocollo Redis (DIAS ↔ ARIA, agnostici):
      Coda task:  aria:q:mus:local:acestep-1.5-xl-sft:dias
      Callback:   aria:c:dias:{job_id}

    Per PAD: ARIA esegue HTDemucs con GPU e ritorna gli URL degli stem
    nel campo output.stems del callback. DIAS scarica tutto via HTTP 8082.
    """

    ARIA_QUEUE = "aria:q:mus:local:acestep-1.5-xl-sft:dias"

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("stage_d2")

        # Output directory
        self.assets_dir = self.persistence.project_root / "stages" / "stage_d2" / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        # Shopping list aggregata (prodotta dal pipeline orchestrator B2)
        self.shopping_list_path = self.persistence.project_root / "sound_shopping_list_aggregata.json"

        # Manifest finale (consumato da Stage E)
        self.manifest_path = self.persistence.project_root / "stages" / "stage_d2" / "manifest.json"

        # Traceability log
        self.trace_log_path = self.persistence.project_root / "stages" / "stage_d2" / "d2_traceability.log"
        self.trace_log_path.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────────

    def _log_trace(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.trace_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [D2] {message}\n")

    # ─────────────────────────────────────────────────────────────
    # HTTP Download (same pattern as Stage D)
    # ─────────────────────────────────────────────────────────────

    def _download_file(self, url: str, dest_path: Path) -> bool:
        """Scarica un file via HTTP con retry (identico a Stage D)."""
        for attempt in range(3):
            try:
                response = requests.get(url, timeout=60, stream=True)
                if response.status_code == 200:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
                else:
                    self.logger.error(f"Download failed (status {response.status_code}): {url}")
            except Exception as e:
                self.logger.error(f"Download attempt {attempt+1}/3 failed for {url}: {e}")
                time.sleep(2)
        return False

    # ─────────────────────────────────────────────────────────────
    # Payload Construction
    # ─────────────────────────────────────────────────────────────

    def _build_lyrics_from_pad_arc(self, pad_arc: list) -> str:
        """
        Converte il pad_arc di B2-Macro in stringa 'lyrics' per ACE-Step in formato LRC.

        Il formato LRC [MM:SS.xx] è OBBLIGATORIO perché il wrapper ARIA usa
        _slice_lyrics_for_chunk() per assegnare a ogni chunk di relay (120s) solo
        la sezione rilevante dell'arco. Se le lyrics non sono in formato LRC,
        il slicer cade nel fallback "pass as-is" → ogni chunk riceve l'arco completo
        → il modello ricomincia l'arco da capo ogni 120s anziché progredire.

        Il timestamp usato è start_s + 1s (1 secondo dopo il bordo del segmento)
        per garantire che cada dentro la finestra del chunk corrispondente.

        Mapping intensità → tag strutturale ACE-Step:
          - Primo segmento            → [Intro]
          - Ultimo segmento           → [Outro]
          - Segmenti mid intermedi    → [Verse]
          - Segmenti high intermedi   → [Chorus]
          - Segmenti pre-high (build) → [Pre-Chorus] (se presenti)
        """
        import re as _re

        if not pad_arc:
            return ""

        n = len(pad_arc)
        lines = []

        for i, seg in enumerate(pad_arc):
            # Determina il tag strutturale
            if i == 0:
                tag = "[Intro]"
            elif i == n - 1:
                tag = "[Outro]"
            else:
                intensity = seg.get("intensity", "mid")
                next_intensity = pad_arc[i + 1].get("intensity") if i + 1 < n else None
                if intensity == "mid" and next_intensity == "high":
                    tag = "[Pre-Chorus]"
                else:
                    tag = _INTENSITY_TO_TAG.get(intensity, "[Verse]")

            # Timestamp LRC: start_s + 1s per garantire che cada nella finestra del chunk.
            # Il slicer del wrapper usa [chunk_start, chunk_end) come finestra.
            start_s = float(seg.get("start_s", 0))
            lrc_t   = start_s + 1.0      # 1s dopo il bordo per stare dentro la finestra
            mm      = int(lrc_t) // 60
            ss      = lrc_t % 60

            # Testo descrittivo breve: solo il tag ACE-Step (no testo lungo — evita voce).
            # Il wrapper imposta instrumental=True per PAD, quindi le lyrics sono
            # puri marcatori strutturali, non testo da cantare.
            roadmap_item = seg.get("roadmap_item", "")
            note         = seg.get("note", "")
            if roadmap_item:
                # roadmap_item formato B2: "[MM:SS - [tag]. Descrizione.]"
                # Estraiamo il contenuto dopo il tag sezione (breve, in inglese)
                desc_match = _re.search(r'\[[\w-]+\]\.\s*(.+?)(?:\.\]?)?$', roadmap_item)
                desc = desc_match.group(1).strip() if desc_match else note
            else:
                desc = note or f"{seg.get('intensity', 'mid').capitalize()} section."

            # Formato LRC standard che il wrapper sa parsare
            lines.append(f"[{mm:02d}:{ss:05.2f}] {tag} {desc}")

        return "\n".join(lines)

    def _build_ace_step_payload(self, asset: Dict) -> Dict[str, Any]:
        """
        Costruisce il payload compatibile con il connettore ARIA ACEStepBackend.run().

        Campi attesi dal connettore (aria_node_controller/backends/acestep.py):
          prompt, lyrics, duration, seed, guidance_scale, inference_steps,
          output_style, thinking, run_demucs, job_id
        """
        asset_type = asset.get("type", "sfx")
        canonical_id = asset.get("canonical_id", "")
        is_pad = asset_type == "pad"
        is_leitmotif = asset_type == "leitmotif"

        # Il prompt viene da B2-Macro v4.2 già in vocabolario ACE-Step nativo.
        # Aggiungiamo solo il prefisso funzionale fisso come guardrail.
        raw_tags = asset.get("production_tags", asset.get("prompt", "cinematic, atmospheric"))
        # Il prefisso funzionale si aggiunge solo per PAD.
        # Leitmotif: ha già il proprio generation_prompt da Stage 0.5 (ACE-Step nativo).
        # AMB/SFX/STING hanno già i propri tag descrittivi — il prefisso musicale
        # causerebbe drift verso output melodici anziché effetti sonori.
        if is_pad and not raw_tags.lower().startswith("cinematic underscore"):
            prompt = _PROMPT_PREFIX + raw_tags
        elif is_leitmotif:
            # Leitmotif: usa generation_prompt (campo primario da Stage 0.5)
            prompt = asset.get("production_prompt", raw_tags)
        else:
            prompt = raw_tags

        # Lyrics: solo per PAD — road map strutturale per il DiT (da pad_arc B2-Macro)
        lyrics = self._build_lyrics_from_pad_arc(asset.get("pad_arc", [])) if is_pad else ""

        duration = float(asset.get("estimated_duration_s") or asset.get("duration_s") or 10.0)

        # job_id nel payload: verrà usato come nome cartella dal wrapper ARIA.
        # Viene ricalcolato uguale a dispatch_to_aria — stesso hash, stesso risultato.
        _full_id = f"{self.project_id}-{canonical_id}"
        _hash    = hashlib.md5(_full_id.encode()).hexdigest()[:10]
        _job_id  = f"d2-{asset_type[:3]}-{_hash}"

        return {
            "job_id":          _job_id,
            "prompt":          prompt,
            "lyrics":          lyrics,
            "duration":        duration,
            "seed":            asset.get("seed", 42),
            "guidance_scale":  float(asset.get("guidance_scale", 4.5 if is_pad else 7.0)),
            "inference_steps": int(asset.get("inference_steps", 60)),
            "output_style":    "music" if is_leitmotif else asset_type,
            "thinking":        is_pad,        # True solo per PAD: evita derail su tracce lunghe
            "run_demucs":      is_pad,        # HTDemucs solo per PAD (stem separati)
        }

    def _build_audiocraft_payload(self, asset: Dict) -> Dict[str, Any]:
        """
        Payload per AudiocraftBackend (AudioGen/MusicGen).
        Campi: prompt, duration, seed, output_style.
        """
        asset_type   = asset.get("type", "sfx")
        canonical_id = asset.get("canonical_id", "")
        raw_tags     = asset.get("production_tags", asset.get("prompt", "atmospheric"))

        _full_id = f"{self.project_id}-{canonical_id}"
        _hash    = hashlib.md5(_full_id.encode()).hexdigest()[:10]
        _job_id  = f"d2-{asset_type[:3]}-{_hash}"

        return {
            "job_id":       _job_id,
            "prompt":       raw_tags,
            "duration":     float(asset.get("estimated_duration_s") or asset.get("duration_s") or 5.0),
            "seed":         asset.get("seed", 42),
            "output_style": asset_type,   # amb | sfx | sting
        }

    # ─────────────────────────────────────────────────────────────
    # ARIA Dispatch (aligned with Stage D pattern)
    # ─────────────────────────────────────────────────────────────

    def dispatch_to_aria(self, asset: Dict) -> Optional[Dict[str, str]]:
        """
        Invia un task ad ARIA via Redis e attende il callback.
        Ritorna un dict con i path locali dei file scaricati, o None su errore.

          PAD:           {"master": "...", "bass": "...", "drums": "...", "other": "..."}
          AMB/SFX/STING: {"master": "..."}

        Timeout PAD: 7200s (relay multi-chunk + HTDemucs GPU lato ARIA).
        Timeout altri: 900s (single-shot, brevi).
        """
        canonical_id   = asset.get("canonical_id")
        asset_type     = asset.get("type", "sfx")
        is_pad         = asset_type == "pad"
        is_leitmotif   = asset_type == "leitmotif"

        # Job ID corto per evitare il limite MAX_PATH di Windows (260 char).
        # Il wrapper crea file come: sound_library/pad/{job_id}/chunks/pt0/{job_id}_pt0.toml
        # Con project_id + canonical_id il path supererebbe 260 char.
        _full_id     = f"{self.project_id}-{canonical_id}"
        _hash        = hashlib.md5(_full_id.encode()).hexdigest()[:10]
        job_id       = f"d2-{asset_type[:3]}-{_hash}"   # es. "d2-pad-a1b2c3d4e5"
        callback_key = f"aria:c:dias:{job_id}"
        timeout      = 7200 if is_pad else (1500 if is_leitmotif else 900)

        use_audiocraft = asset_type in ("amb", "sfx", "sting")
        task = {
            "job_id":          job_id,
            "client_id":       "dias",
            "model_type":      "mus",
            "model_id":        "audiocraft-medium" if use_audiocraft else "acestep-1.5-xl-sft",
            "payload":         self._build_audiocraft_payload(asset) if use_audiocraft else self._build_ace_step_payload(asset),
            "callback_key":    callback_key,
            "timeout_seconds": timeout,
        }

        self._log_trace(f"SUBMIT → {self.ARIA_QUEUE} | {canonical_id} ({asset_type}) | timeout={timeout}s")
        self.logger.info(f"🚀 Task ARIA: {canonical_id} ({asset_type}) | durata={task['payload']['duration']}s")

        self.redis.client.lpush(self.ARIA_QUEUE, json.dumps(task))

        self.logger.info(f"⏳ Attesa callback: {callback_key} (max {timeout}s)...")
        # Polling loop a finestre da 60s per stare dentro socket_timeout del client Redis.
        # Ogni iterazione fa brpop(60s); se scade reitera fino al deadline totale.
        deadline = time.time() + timeout
        result_raw = None
        while time.time() < deadline:
            remaining = int(deadline - time.time())
            poll_t = min(60, remaining)
            if poll_t <= 0:
                break
            result_raw = self.redis.client.brpop(callback_key, timeout=poll_t)
            if result_raw:
                break

        if not result_raw:
            self.logger.error(f"❌ Timeout ({timeout}s) per {canonical_id}")
            self._log_trace(f"TIMEOUT {canonical_id}")
            return None

        _, result_json = result_raw
        result = json.loads(result_json)

        # L'orchestratore ARIA wrappa in AriaTaskResult → status="done" su successo
        if result.get("status") != "done":
            error = result.get("error", "Errore sconosciuto")
            self.logger.error(f"❌ ARIA error per {canonical_id}: {error}")
            self._log_trace(f"ERRORE {canonical_id}: {error}")
            return None

        output    = result.get("output", {})
        audio_url = output.get("audio_url")
        if not audio_url:
            self.logger.error(f"❌ Nessun audio_url nel callback per {canonical_id}")
            return None

        # ── Download master WAV ───────────────────────────────────────────────
        type_dir    = self.assets_dir / asset_type
        master_path = type_dir / f"{canonical_id}.wav"
        local_paths: Dict[str, str] = {}

        if self._download_file(audio_url, master_path):
            local_paths["master"] = str(master_path)
            self._log_trace(f"Master OK: {master_path.name}")
        else:
            self.logger.error(f"❌ Download master fallito per {canonical_id}")
            return None

        # ── Download stem WAV (solo PAD — ARIA li produce con HTDemucs GPU) ──
        if is_pad:
            stems_data = output.get("stems", {})
            stems_dir  = type_dir / "stems" / canonical_id
            for stem_name in DEMUCS_STEMS:
                stem_url = stems_data.get(stem_name)
                if stem_url:
                    stem_path = stems_dir / f"{stem_name}.wav"
                    if self._download_file(stem_url, stem_path):
                        local_paths[stem_name] = str(stem_path)
                        self._log_trace(f"  Stem {stem_name}: OK")
                    else:
                        self.logger.warning(f"⚠️ Download stem '{stem_name}' fallito per {canonical_id}")
                else:
                    self.logger.warning(f"⚠️ Stem '{stem_name}' non presente nel callback per {canonical_id}")

        duration = output.get("duration_seconds", 0)
        stems_ok  = len(local_paths) - 1  # escludi "master"
        self.logger.info(
            f"✅ {canonical_id}: master"
            + (f" + {stems_ok} stem" if is_pad else "")
            + (f" ({duration:.1f}s)" if duration else "")
        )

        return local_paths

    # ─────────────────────────────────────────────────────────────
    # Leitmotif Loader
    # ─────────────────────────────────────────────────────────────

    def _load_leitmotif_items(self) -> list:
        """
        Legge project_sound_palette da preproduction.json e costruisce la lista
        di asset leitmotif da produrre tramite ACE-Step (stessa pipeline del PAD,
        ma senza HTDemucs). Ritorna lista vuota se la palette non esiste o è già
        presente come WAV nella cartella assets/leitmotif/.
        """
        preprod_path = self.persistence.get_preproduction_path()
        if not preprod_path or not preprod_path.exists():
            return []

        with open(preprod_path, encoding="utf-8") as f:
            preprod = json.load(f)

        palette = preprod.get("project_sound_palette", {})
        if not palette:
            return []

        items = []
        leitmotif_dir = self.assets_dir / "leitmotif"
        for cid, entry in palette.items():
            # Idempotency: skip se WAV già presente
            wav_path = leitmotif_dir / f"{cid}.wav"
            if wav_path.exists() and wav_path.stat().st_size > 1000:
                self.logger.info(f"🎯 Local Hit leitmotif: {cid}")
                continue

            items.append({
                "type":             "leitmotif",
                "canonical_id":     cid,
                "production_tags":  entry.get("generation_tags", ""),
                "production_prompt": entry.get("generation_prompt", ""),
                "negative_prompt":  entry.get("negative_prompt", ""),
                "duration_s":       float(entry.get("duration_s", 24)),
                "seed":             int(entry.get("seed", 42)),
                "guidance_scale":   float(entry.get("guidance_scale", 7.0)),
                "inference_steps":  int(entry.get("inference_steps", 60)),
            })

        return items

    def _update_leitmotif_paths(self, cid: str, wav_path: str) -> None:
        """Aggiorna local_wav in preproduction.json dopo produzione ARIA."""
        preprod_path = self.persistence.get_preproduction_path()
        if not preprod_path or not preprod_path.exists():
            return
        with open(preprod_path, encoding="utf-8") as f:
            preprod = json.load(f)
        palette = preprod.get("project_sound_palette", {})
        if cid in palette:
            palette[cid]["local_wav"] = wav_path
            palette[cid]["generated_at"] = datetime.now().isoformat()
            with open(preprod_path, "w", encoding="utf-8") as f:
                json.dump(preprod, f, indent=2, ensure_ascii=False)

    # ─────────────────────────────────────────────────────────────
    # Main Run
    # ─────────────────────────────────────────────────────────────

    def dry_run(self):
        """
        Costruisce e salva tutti i payload ARIA senza inviare nulla a Redis.
        Output: stages/stage_d2/d2_dry_run_payloads.json
        """
        if not self.shopping_list_path.exists():
            self.logger.error(f"❌ Shopping list non trovata: {self.shopping_list_path}")
            return

        with open(self.shopping_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_assets = data.get("assets", [])
        seen = set()
        assets_to_process = []
        for asset in all_assets:
            cid = asset["canonical_id"]
            if cid not in seen:
                seen.add(cid)
                assets_to_process.append(asset)

        payloads = []
        for asset in assets_to_process:
            cid          = asset.get("canonical_id")
            asset_type   = asset.get("type", "sfx")
            is_pad       = asset_type == "pad"
            is_leitmotif = asset_type == "leitmotif"
            _full_id     = f"{self.project_id}-{cid}"
            import hashlib as _hl
            _hash        = _hl.md5(_full_id.encode()).hexdigest()[:10]
            job_id       = f"d2-{asset_type[:3]}-{_hash}"
            callback_key = f"aria:c:dias:{job_id}"
            timeout      = 7200 if is_pad else (1500 if is_leitmotif else 900)

            use_audiocraft = asset_type in ("amb", "sfx", "sting")
            payload      = self._build_audiocraft_payload(asset) if use_audiocraft else self._build_ace_step_payload(asset)

            redis_task = {
                "job_id":          job_id,
                "client_id":       "dias",
                "model_type":      "mus",
                "model_id":        "audiocraft-medium" if use_audiocraft else "acestep-1.5-xl-sft",
                "payload":         payload,
                "callback_key":    callback_key,
                "timeout_seconds": timeout,
            }

            payloads.append({
                "canonical_id":  cid,
                "type":          asset_type,
                "redis_queue":   self.ARIA_QUEUE,
                "callback_key":  callback_key,
                "timeout_s":     timeout,
                "redis_task":    redis_task,
            })

        out_path = self.trace_log_path.parent / "d2_dry_run_payloads.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payloads, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Dry-run completato: {len(payloads)} payload generati")
        print(f"   Salvati in: {out_path}")
        print(f"\n{'─'*60}")
        for p in payloads:
            pl = p["redis_task"]["payload"]
            lyr_preview = pl.get("lyrics", "")[:80].replace("\n", " | ") if pl.get("lyrics") else "—"
            print(f"  [{p['type'].upper():5s}] {p['canonical_id']}")
            print(f"         job_id   : {p['redis_task']['job_id']}")
            print(f"         duration : {pl.get('duration')}s | guidance: {pl.get('guidance_scale')} | steps: {pl.get('inference_steps')}")
            print(f"         demucs   : {pl.get('run_demucs')} | thinking: {pl.get('thinking')}")
            print(f"         prompt   : {pl.get('prompt', '')[:100]}")
            print(f"         lyrics   : {lyr_preview}")
            print()

    def run(self):
        """Esegue l'intero processo di produzione per il progetto."""
        if not self.shopping_list_path.exists():
            self.logger.error(f"❌ Shopping list non trovata: {self.shopping_list_path}")
            return

        with open(self.shopping_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_assets = data.get("assets", [])

        # Prepend leitmotif_creation items (from Stage 0.5, highest priority)
        leitmotif_items = self._load_leitmotif_items()
        if leitmotif_items:
            self.logger.info(f"🎵 {len(leitmotif_items)} leitmotif da produrre (Stage 0.5)")
        all_assets = leitmotif_items + all_assets

        # Deduplicazione per canonical_id
        seen = set()
        assets_to_process = []
        for asset in all_assets:
            cid = asset["canonical_id"]
            if cid not in seen:
                seen.add(cid)
                assets_to_process.append(asset)

        self.logger.info(f"🚀 Avvio Stage D2 per {len(assets_to_process)} asset unici (da {len(all_assets)} totali).")
        self._log_trace(f"{'='*60}")
        self._log_trace(f"START D2 — {len(assets_to_process)} asset unici")

        manifest = {
            "project_id": self.project_id,
            "generated_at": datetime.now().isoformat(),
            "assets": {},
        }

        for asset in assets_to_process:
            cid = asset["canonical_id"]
            asset_type = asset["type"]
            is_pad = asset_type == "pad"

            # Idempotency check: master già presente?
            type_dir = self.assets_dir / asset_type
            master_path = type_dir / f"{cid}.wav"

            if master_path.exists() and master_path.stat().st_size > 1000:
                self.logger.info(f"🎯 Local Hit: {cid} già presente. Salto produzione.")
                self._log_trace(f"SKIP (locale): {cid}")

                local_paths = {"master": str(master_path)}

                # Check stems per PAD
                if is_pad:
                    stems_dir = type_dir / "stems" / cid
                    for stem_name in DEMUCS_STEMS:
                        stem_file = stems_dir / f"{stem_name}.wav"
                        if stem_file.exists():
                            local_paths[stem_name] = str(stem_file)
            else:
                # Produzione via ARIA
                local_paths = self.dispatch_to_aria(asset)

            if not local_paths:
                self.logger.error(f"❌ Impossibile ottenere {cid}. Salto.")
                self._log_trace(f"FALLITO: {cid}")
                continue

            # Aggiorna local_wav in preproduction.json per i leitmotif
            if asset_type == "leitmotif":
                self._update_leitmotif_paths(cid, local_paths.get("master", ""))

            # Build manifest entry
            asset_entry = {
                "type": asset_type,
                "master_path": local_paths.get("master", ""),
                "duration_s": asset.get("estimated_duration_s", asset.get("duration_s")),
                "status": "ready",
            }

            if is_pad:
                asset_entry["stems"] = {
                    name: local_paths.get(name, "")
                    for name in DEMUCS_STEMS
                    if local_paths.get(name)
                }

            manifest["assets"][cid] = asset_entry

        # Salvataggio Manifest
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        self.logger.info(f"✅ Stage D2 completato. Manifest: {self.manifest_path}")
        self._log_trace(f"END D2 — Manifest generato con {len(manifest['assets'])} asset")
        self._log_trace(f"{'='*60}")


if __name__ == "__main__":
    import argparse as _ap
    parser = _ap.ArgumentParser(description="DIAS Stage D2 — Sound Factory Client")
    parser.add_argument("project_id", help="ID del progetto")
    parser.add_argument("--dry-run", action="store_true",
                        help="Costruisce i payload ARIA senza inviare a Redis")
    args = parser.parse_args()

    stage = StageD2SoundFactory(args.project_id)
    if args.dry_run:
        stage.dry_run()
    else:
        stage.run()
