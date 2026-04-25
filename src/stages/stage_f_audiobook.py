#!/usr/bin/env python3
import json
import os
import sys
import wave
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.persistence import DiasPersistence
from src.common.logging_setup import get_logger
from src.common.redis_factory import get_redis_client

logger = get_logger("stage_f_audiobook")

def duration_ms_of_wav(wav_path: Path) -> int:
    """Restituisce la durata del WAV in millisecondi."""
    try:
        with wave.open(str(wav_path), 'rb') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return int((frames / float(rate)) * 1000)
    except Exception as e:
        logger.error(f"Errore nella lettura di {wav_path}: {e}")
        return 0

def build_audiobook(project_id: str):
    logger.info(f"🎧 Inizio Mastering Audiobook per il progetto: {project_id}")
    persistence = DiasPersistence(project_id=project_id)
    project_root = persistence.project_root
    
    stage_c_dir = project_root / "stages" / "stage_c" / "output"
    stage_d_dir = project_root / "stages" / "stage_d" / "output"
    
    logger.info(f"Checking for WAVs in: {stage_d_dir.resolve()}")
    
    final_dir = project_root / "final"
    final_dir.mkdir(exist_ok=True)
    
    output_m4b = final_dir / f"{project_id}.m4b"
    metadata_txt = final_dir / "metadata.txt"
    concat_txt = final_dir / "concat_list.txt"
    
    # 1. Trova e ordina tutti i WAV - Cerchiamo file che contengono il project_id
    wav_files = sorted(list(stage_d_dir.glob("*.wav")))
    # Filtriamo per assicurarci che siano del progetto (caso mai ci siano residui)
    wav_files = [f for f in wav_files if project_id in f.name]
    
    if not wav_files:
        logger.error(f"Nessun file WAV trovato in {stage_d_dir.resolve()}")
        return False
        
    logger.info(f"Trovati {len(wav_files)} file WAV vocali. Esecuzione mappatura Capitoli...")
    
    # 2a. Carica titoli capitoli e mappa subtitle→chapter_id da fingerprint.json
    # chapter_id = chapter_{i+1:03d} (positional, 1-based) — uniform across all project types
    chapter_titles: Dict[str, str] = {}
    subtitle_to_chapter: Dict[str, str] = {}
    ordinal_to_chapter: Dict[int, str] = {}  # ordinal number → chapter_id

    _ROMAN_MAP = {
        "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
        "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
        "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19,
        "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24,
        "XXV": 25, "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
    }

    # Try fingerprint at project root first, then stages/stage_0/output/
    _fp_candidates = [
        project_root / "fingerprint.json",
        project_root / "stages" / "stage_0" / "output" / "fingerprint.json",
    ]
    fingerprint_path = next((p for p in _fp_candidates if p.exists()), None)

    if fingerprint_path:
        try:
            with open(fingerprint_path, "r", encoding="utf-8") as f:
                fp = json.load(f)
            chapters_raw = fp.get("chapters", fp.get("chapters_list", []))
            for i, ch in enumerate(chapters_raw):
                cid = f"chapter_{i + 1:03d}"
                name = ch.get("title", ch.get("name", ""))
                chapter_titles[cid] = name

                # Subtitle map: text after "Capitolo X: " for fuzzy match in scene text
                parts = name.split(": ", 1)
                subtitle = (parts[1] if len(parts) > 1 else name).strip().lower()
                if subtitle:
                    subtitle_to_chapter[subtitle] = cid

                # Ordinal map: extract Roman or plain int from prefix ("Capitolo XIV" → 14)
                prefix = parts[0].strip() if len(parts) > 1 else ""
                prefix_tokens = prefix.split()
                if len(prefix_tokens) >= 2:
                    ordinal_token = prefix_tokens[-1].upper()
                    ordinal_num = _ROMAN_MAP.get(ordinal_token)
                    if ordinal_num is None:
                        try:
                            ordinal_num = int(ordinal_token)
                        except ValueError:
                            pass
                    if ordinal_num:
                        ordinal_to_chapter[ordinal_num] = cid

            logger.info(
                f"Caricati {len(chapter_titles)} capitoli da fingerprint "
                f"({len(subtitle_to_chapter)} sottotitoli, {len(ordinal_to_chapter)} ordinali)"
            )
        except Exception as e:
            logger.warning(f"Impossibile caricare fingerprint: {e}")

    # 2b. Leggi Mapping Scene -> dati dalla Scene Grid (Stage C)
    # Stage C scrive un file JSON per ogni scena (non raggruppati).
    # Il chapter_id da Stage C è hardcodato (bug upstream); usiamo scene_label + text_content
    # per rilevare i confini capitolo dalle scene "Narratore — titolo".
    scene_data: Dict[str, Dict] = {}

    for jf in stage_c_dir.glob("*.json"):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            s_id = data.get("scene_id")
            if s_id:
                scene_data[s_id] = {
                    "pause_after_ms": data.get("pause_after_ms", 1000),
                    "scene_label": data.get("scene_label", ""),
                    "text_content": data.get("text_content", ""),
                }
        except Exception:
            pass

    logger.info(f"Mappate {len(scene_data)} scene da Stage C")

    # 3. Costruzione Metadata & Concat List
    with open(concat_txt, "w", encoding="utf-8") as cfile:
        for wav_path in wav_files:
            # escaping automatico di FFmpeg per i path
            abs_p = str(wav_path).replace("'", "'\\''")
            cfile.write(f"file '{abs_p}'\n")

    metadata_blocks = [";FFMETADATA1\n"]

    current_chapter: str | None = None
    chapter_start_time = 0
    current_time_ms = 0

    for wav_path in wav_files:
        # Trova il scene_id dal filename. Esempio: project_id-chunk-000-micro-000-scene-001.wav
        filename = wav_path.name
        # Rimuoviamo l'estensione e il prefisso project_id (la chiave in Stage C è 'chunk-...')
        scene_id = filename.replace(".wav", "").replace(f"{project_id}-", "")

        info = scene_data.get(scene_id, {})

        # Rileva confine capitolo: scene il cui testo inizia con "Capitolo " e corrisponde
        # a un sottotitolo del fingerprint (Stage A non propaga chapter_id correttamente).
        # Usiamo il testo come segnale primario perché scene_label varia ("titolo", "cornice", ecc.)
        chapter_id = current_chapter  # default: mantieni capitolo corrente
        text_lower = info.get("text_content", "").strip().lower()

        # Detect chapter boundary: scene text starts with "capitolo " (or "chapter ")
        _chapter_keywords = ("capitolo ", "chapter ", "parte ")
        _starts_with_chapter = any(text_lower.startswith(kw) for kw in _chapter_keywords)

        if chapter_titles and _starts_with_chapter:
            # Strategy 1: subtitle match (text after "Capitolo X: ")
            matched = False
            for subtitle, cid in subtitle_to_chapter.items():
                if subtitle and subtitle in text_lower:
                    chapter_id = cid
                    matched = True
                    break

            if not matched:
                # Strategy 2: ordinal extraction — Italian cardinal or Roman numeral
                _IT_CARD = {
                    "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
                    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
                    "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14,
                    "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
                    "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22,
                    "ventitré": 23, "ventitre": 23, "ventiquattro": 24, "venticinque": 25,
                    "ventisei": 26, "ventisette": 27, "ventotto": 28,
                    "primo": 1, "secondo": 2, "terzo": 3, "quarto": 4, "quinto": 5,
                    "sesto": 6, "settimo": 7, "ottavo": 8, "nono": 9, "decimo": 10,
                    "undicesimo": 11, "dodicesimo": 12, "tredicesimo": 13,
                    "quattordicesimo": 14, "quindicesimo": 15, "sedicesimo": 16,
                    "diciassettesimo": 17, "diciottesimo": 18, "diciannovesimo": 19,
                }
                # Strip the keyword prefix and extract first token
                remaining = text_lower
                for kw in _chapter_keywords:
                    if remaining.startswith(kw):
                        remaining = remaining[len(kw):]
                        break
                first_token = remaining.split()[0].rstrip(":.,") if remaining.split() else ""

                # Try Italian cardinal
                num = _IT_CARD.get(first_token)
                # Try Roman numeral
                if num is None:
                    num = _ROMAN_MAP.get(first_token.upper())
                # Try plain integer
                if num is None:
                    try:
                        num = int(first_token)
                    except ValueError:
                        pass

                if num and num in ordinal_to_chapter:
                    chapter_id = ordinal_to_chapter[num]
                    logger.debug(f"Ordinal fallback: '{first_token}' → {num} → {chapter_id}")

        # Primo WAV: inizializza capitolo di default se nessun marker trovato
        if chapter_id is None:
            chapter_id = "chapter_001"

        # Gestiamo il marker dei capitoli
        if current_chapter != chapter_id:
            # Abbiamo chiuso il capitolo precedente?
            if current_chapter is not None:
                metadata_blocks.append("[CHAPTER]")
                metadata_blocks.append("TIMEBASE=1/1000")
                metadata_blocks.append(f"START={chapter_start_time}")
                metadata_blocks.append(f"END={current_time_ms}")
                # Format pulito (es. "chapter_001" -> "Chapter 1")
                friendly_name = chapter_titles.get(current_chapter, current_chapter.replace("_", " ").capitalize())
                metadata_blocks.append(f"title={friendly_name}\n")
            
            # Apriamo il nuovo
            current_chapter = chapter_id
            chapter_start_time = current_time_ms
            
        dur_ms = duration_ms_of_wav(wav_path)
        current_time_ms += dur_ms
    
    # Chiusura dell'ultimo capitolo
    if current_chapter is not None:
        metadata_blocks.append("[CHAPTER]")
        metadata_blocks.append("TIMEBASE=1/1000")
        metadata_blocks.append(f"START={chapter_start_time}")
        metadata_blocks.append(f"END={current_time_ms}")
        friendly_name = chapter_titles.get(current_chapter, current_chapter.replace("_", " ").capitalize())
        metadata_blocks.append(f"title={friendly_name}\n")

    with open(metadata_txt, "w", encoding="utf-8") as mfile:
        mfile.write("\n".join(metadata_blocks))

    # 4. FFMPEG Muxing (Concat -> M4B con Chapter Marks)
    # FFmpeg concat muxer richiede -f concat e -safe 0
    # map_metadata 1 carica il file metadata come traccia globale
    
    logger.info("Avvio codifica con FFmpeg (AAC M4B) in modalità LIGHT (1-core, low priority)...")
    ffmpeg_cmd = [
        "nice", "-n", "19",
        "ffmpeg", "-y",
        "-threads", "1",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-i", str(metadata_txt),
        "-map_metadata", "1",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", # Audiobook optimal
        str(output_m4b)
    ]
    
    try:
        # Redirect stdout to DEVNULL to avoid filling logs, capture stderr for errors
        process = subprocess.run(
            ffmpeg_cmd, 
            cwd=project_root, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error (RC {process.returncode}): {process.stderr}")
            return False

        logger.info(f"✅ Audiobook completato con successo: {output_m4b}")
        
        # Aggiorniamo il config
        config_path = project_root / "config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                cfg = json.load(f)
            cfg["status"] = "completed"
            cfg["last_stage"] = "stage_f"
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=4)
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr.decode('utf-8')}")
        return False

def listen_queue():
    redis = get_redis_client()
    queue_name = "dias:q:0:mastering"
    
    logger.info(f"Ascolto sulla coda Audiobook Mastering ({queue_name})...")
    while True:
        try:
            # Il metodo corretto è consume_from_queue
            msg = redis.consume_from_queue(queue_name, timeout=5)
            if msg:
                project_id = msg.get("project_id")
                if not project_id: continue
                
                redis.set(f"dias:project:{project_id}:active_stage", "stage_f")
                redis.client.hset(f"dias:project:{project_id}:status", "stage_f_progress", "10") # 10% started
                
                success = build_audiobook(project_id)
                
                if success:
                    redis.client.hset(f"dias:project:{project_id}:status", "stage_f_progress", "100")
                else:
                    redis.client.hset(f"dias:project:{project_id}:status", "stage_f_error", "ffmpeg failed")
                
                redis.client.delete(f"dias:project:{project_id}:active_stage")
        except Exception as e:
            logger.error(f"Eccezione in Stage F worker loop: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--queue":
        build_audiobook(sys.argv[1])
    else:
        listen_queue()
