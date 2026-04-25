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
    
    # 2a. Carica titoli capitoli da fingerprint.json (Stage 0)
    chapter_titles: Dict[str, str] = {}
    fingerprint_path = project_root / "stages" / "stage_0" / "output" / "fingerprint.json"
    if fingerprint_path.exists():
        try:
            with open(fingerprint_path, "r", encoding="utf-8") as f:
                fp = json.load(f)
            for ch in fp.get("chapters_list", []):
                chapter_titles[f"chapter_{ch['id']}"] = ch["name"]
            logger.info(f"Caricati {len(chapter_titles)} titoli capitoli da fingerprint")
        except Exception as e:
            logger.warning(f"Impossibile caricare fingerprint: {e}")

    # 2b. Leggi Mapping Scene -> Capitolo & Pause dalla Scene Grid (Stage C)
    scene_data: Dict[str, Dict] = {}

    scene_json_files = list(stage_c_dir.glob("*-scenes.json"))
    for jf in scene_json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            scenes = data.get("scenes", [])
            for s in scenes:
                # Usa il nome corretto scene_id o componilo nel dubbio
                # I file WAV di stage_d contengono il project_id prima del chunk
                s_id = s.get("scene_id")
                if s_id:
                    scene_data[s_id] = {
                        "chapter_id": s.get("chapter_id", "Chapter"),
                        "pause_after_ms": s.get("pause_after_ms", 1000)
                    }

    # 3. Costruzione Metadata & Concat List
    with open(concat_txt, "w", encoding="utf-8") as cfile:
        for wav_path in wav_files:
            # escaping automatico di FFmpeg per i path
            abs_p = str(wav_path).replace("'", "'\\''")
            cfile.write(f"file '{abs_p}'\n")

    metadata_blocks = [";FFMETADATA1\n"]
    
    current_chapter = None
    chapter_start_time = 0
    current_time_ms = 0
    
    for wav_path in wav_files:
        # Trova il scene_id dal filename. Esempio: project_id-chunk-000-micro-000-scene-001.wav
        filename = wav_path.name
        # Rimuoviamo l'estensione e il prefisso project_id (la chiave in Stage C è 'chunk-...')
        scene_id = filename.replace(".wav", "").replace(f"{project_id}-", "")
        
        info = scene_data.get(scene_id, {"chapter_id": "Unknown Chapter", "pause_after_ms": 1000})
        chapter_id = info["chapter_id"]
        
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
        friendly_name = current_chapter.replace("_", " ").capitalize()
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
