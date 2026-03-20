#!/usr/bin/env python3
"""
Stage D - Voice Generator (ARIA Proxy)

Questo stadio non esegue il TTS localmente. Invece:
1. Consuma SceneScript dallo Stage C.
2. Invia una task all'Orchestratore ARIA su Windows via Redis.
3. Aspetta il risultato (URL del file generato).
4. Aggiorna lo stato DIAS per lo Stage E.
"""

import os
import json
import logging
import time
import requests
import sys
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
from datetime import datetime

# Aggiungi il path root al Python path per trovare il modulo 'src'
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.base_stage import BaseStage
from src.common.models import SceneScript, TTSBackend
from src.common.persistence import DiasPersistence

class StageDVoiceGeneratorProxy(BaseStage):
    """
    Stage D: Voice Generator Proxy for ARIA
    """
    
    def __init__(self, redis_client=None, config=None):
        print("DEBUG: StageDProxy.__init__ started")
        super().__init__(
            stage_name="stage_d_voice_gen",
            stage_number=4,
            input_queue="dias:queue:4:voice",
            output_queue="dias:queue:5:music_gen",
            config=config,
            redis_client=redis_client
        )
        self.persistence = DiasPersistence()
        from src.common.registry import ActiveTaskTracker
        print("DEBUG: ActiveTaskTracker imported")
        self.tracker = ActiveTaskTracker(self.redis, self.logger)
        print("DEBUG: StageDProxy.__init__ completed")
        
        # Configurazione ARIA
        self.aria_tts_queue = "gpu:queue:tts:qwen3-tts-1.7b"
        self.enable_dynamic_params = os.getenv("ENABLE_DYNAMIC_PARAMS", "false").lower() == "true"
        
        # Reference fisso per narratore (da documentazione ARIA)
        self.voice_ref_text = "Leggi la Bibbia, Brett? E allora ascolta questo passo che conosco a memoria, è perfetto per l'occasione: Ezechiele 25:17. Il cammino dell'uomo timorato è minacciato da ogni parte dalle iniquità degli esseri egoisti e dalla tirannia degli uomini malvagi. Benedetto sia colui che nel nome della carità e della buona volontà conduce i deboli attraverso la valle"
        self.voice_ref_path = "C:\\Users\\Roberto\\aria\\data\\voices\\narratore.wav"

    def process(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Invia la scena ad ARIA e attende il risultato.
        """
        try:
            job_id = message.get("job_id")
            book_id = message.get("book_id")
            scene_id = message.get("scene_id")

            self.logger.info(f"Processing Stage D Proxy: Book {book_id} - Scene {scene_id}")
            
            # 1. Recupera dati completi della scena
            if "text_content" not in message:
                self.logger.warning("Messaggio incompleto, caricamento da persistenza...")
                return None

            # 2. Prepara il payload per ARIA
            text_to_speak = message.get("fish_annotated_text") or message.get("text_content")
            
            # Parametri dinamici
            temp = 0.7
            top_p = 0.8
            if self.enable_dynamic_params:
                voice_dir = message.get("voice_direction", {})
                tension = voice_dir.get("energy", 0.5)
                temp = 0.6 + (tension * 0.2)
            
            callback_key = f"dias:callback:stage_d:{job_id}:{scene_id}"
            
            # Genera un job_id univoco e in sequenza logica per la costruzione del file in ARIA
            clean_title = message.get("clean_title") or "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            chunk_label = message.get("chunk_label") or "chunk-000"
            unique_aria_job_id = f"{clean_title}-{chunk_label}-{scene_id}"

            # --- REMOTE SKIP LOGIC (Coherence Check) ---
            # Verifichiamo se l'asset esiste già sul PC Gaming (Orchestrator Asset Server :8082)
            # Questo permette di saltare la generazione anche se Redis è vuoto o il registro è inconsistente.
            aria_host = os.getenv("ARIA_HOST", "192.168.1.139")
            aria_asset_port = os.getenv("ARIA_ASSET_PORT", "8082")
            expected_url = f"http://{aria_host}:{aria_asset_port}/{unique_aria_job_id}.wav"
            
            self.logger.info(f"Checking for remote asset existence: {expected_url}")
            try:
                head_resp = requests.head(expected_url, timeout=5)
                if head_resp.status_code == 200:
                    self.logger.info(f"🎯 Remote Hit! Scena {unique_aria_job_id} già esistente su ARIA. Saltando task.")
                    
                    # Recupera durata se possibile dai visti (opzionale, o usiamo stimata)
                    duration = message.get("timing_estimate", {}).get("estimated_duration_seconds", 0)
                    
                    # Aggiorna registro e ritorna successo immediato
                    self.tracker.mark_as_completed(book_id, unique_aria_job_id, expected_url)
                    message["voice_path"] = expected_url
                    message["voice_duration_seconds"] = duration
                    message["voice_status"] = "completed"
                    
                    # Salva checkpoint locale
                    self.persistence.save_stage_output("d", message, clean_title, chunk_label, scene_id)
                    return message
            except Exception as e:
                self.logger.warning(f"Remote check fallito per {expected_url}: {e}")

            # Istruzione Stilistica Dinamica (Qwen3-TTS)
            default_instruct = "Warm Italian male voice, professional audiobook narrator."
            instruct = message.get("qwen3_instruct") or default_instruct
            
            # --- Configurazione Backend Dinamica (SOA v2.1) ---
            # Compatibilità con chiavi tts_model_id (Registry) o tts_backend (Stage C)
            target_model = message.get("tts_model_id") or message.get("tts_backend") or os.getenv("DEFAULT_TTS_MODEL_ID", "qwen3-tts-1.7b")
            
            # Align with ARIA Canonical Standard (SOA v2.1)
            # Schema: global:queue:{model_type}:{provider}:{model_id}:{client_id}
            self.aria_tts_queue = f"global:queue:tts:local:{target_model}:dias_pipeline"
            
            aria_task = {
                "job_id": unique_aria_job_id,
                "client_id": "dias_pipeline",
                "model_type": "tts",
                "model_id": target_model,  # Passiamo il modello specifico ad ARIA
                "payload": {
                    "job_id": unique_aria_job_id,
                    "text": text_to_speak,
                    "voice_id": message.get("voice_id", "luca"),
                    "instruct": instruct,
                    "temperature": temp,
                    "top_p": top_p,
                    "output_format": "wav"
                },
                "callback_key": callback_key,
                "timeout_seconds": 600  # Timeout incrementato per swap modello JIT
            }
            
            # 3. Master Registry Check (Idempotency & Resilience)
            if not self.tracker.is_task_ready_to_send(book_id, unique_aria_job_id):
                entry = self.tracker.get_entry(book_id, unique_aria_job_id)
                if entry and entry.status == "COMPLETED":
                    self.logger.info(f"Scena {unique_aria_job_id} già completata nel registro. Recupero output rintracciabile.")
                    message["voice_path"] = entry.output_path
                    message["voice_duration_seconds"] = entry.metadata.get("duration_seconds", 0)
                    message["voice_status"] = "completed"
                    return message
                
                self.logger.info(f"Scena {unique_aria_job_id} già in corso (IN_FLIGHT). Salto sottomissione ed entro in ascolto callback.")
            else:
                self.logger.info(f"Sottomissione task TTS ad ARIA per scena {unique_aria_job_id}")
                self.tracker.mark_as_inflight(book_id, unique_aria_job_id, callback_key)
                self.redis.push_to_queue(self.aria_tts_queue, aria_task)
            
            # 4. Attesa Risultato (LPUSH + EXPIRE su ARIA side, BRPOP qui)
            self.logger.info(f"In attesa di risultato su {callback_key} (timeout 900s)...")
            result_raw = self.redis.consume_from_queue(callback_key, timeout=900)
            
            if not result_raw:
                error_msg = f"Timeout attesa risultato ARIA per scena {unique_aria_job_id}"
                self.logger.error(error_msg)
                self.tracker.mark_as_failed(book_id, unique_aria_job_id, error_msg)
                return None
                
            aria_result = result_raw
            if aria_result.get("status") != "done":
                error_msg = f"Errore ARIA: {aria_result.get('error')}"
                self.logger.error(error_msg)
                self.tracker.mark_as_failed(book_id, unique_aria_job_id, error_msg)
                return None
            
            final_url = aria_result.get("output", {}).get("audio_url")
            duration = aria_result.get("output", {}).get("duration_seconds")
            
            self.logger.info(f"Scena {unique_aria_job_id} generata con successo: {final_url}")
            
            # 5. Aggiorna Master Registry e passa a Stage E
            self.tracker.mark_as_completed(book_id, unique_aria_job_id, final_url)
            # Aggiorniamo anche i metadati nel registro
            entry = self.tracker.get_entry(book_id, unique_aria_job_id)
            if entry:
                entry.metadata["duration_seconds"] = duration
                self.tracker.set_entry(book_id, entry)

            message["voice_path"] = final_url
            message["voice_duration_seconds"] = duration
            message["voice_status"] = "completed"
            
            # Salva checkpoint locale
            clean_title = message.get("clean_title") or "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            chunk_label = message.get("chunk_label") or "chunk-000"
            self.persistence.save_stage_output("d", message, clean_title, chunk_label, scene_id)
            
            return message
            
        except Exception as e:
            self.logger.error(f"Errore nello Stage D Proxy: {e}", exc_info=True)
            return None

if __name__ == "__main__":
    stage = StageDVoiceGeneratorProxy()
    stage.run()
