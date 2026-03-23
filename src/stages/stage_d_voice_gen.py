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
            input_queue=None, # Set below
            output_queue=None, # Set below
            config=config,
            redis_client=redis_client
        )
        self.input_queue = self.cfg.queues.voice
        self.output_queue = self.cfg.queues.music
        self.persistence = DiasPersistence()
        from src.common.registry import ActiveTaskTracker
        print("DEBUG: ActiveTaskTracker imported")
        self.tracker = ActiveTaskTracker(self.redis, self.logger)
        print("DEBUG: StageDProxy.__init__ completed")
        
        # Reference fisso per narratore (da documentazione ARIA)
        # Nota: Questi potrebbero anche essere esternalizzati in futuro
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

            # Genera identificatori unici per il task e file
            clean_title = message.get("clean_title") or "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            chunk_label = message.get("chunk_label") or "chunk-000"
            unique_aria_job_id = f"{clean_title}-{chunk_label}-{scene_id}"

            # --- SETUP DIRECTORY LOCALE (LXC 190) ---
            # Correzione: rimosso "data" ridondante (gia' presente in base_path)
            # Organizzazione: Piatto dentro la cartella del libro (per separare WAV da JSON)
            local_dir = self.persistence.base_path / "stage_d" / "output" / clean_title
            local_dir.mkdir(parents=True, exist_ok=True)
            local_filename = f"{unique_aria_job_id}.wav"
            local_path = local_dir / local_filename

            # === STEP 1: CHECK LOCALE (LXC 190) ===
            if local_path.exists() and local_path.stat().st_size > 1000:
                self.logger.info(f"🎯 Local Hit! Scena {unique_aria_job_id} già presente in locale {local_path}. Saltando task.")
                duration = message.get("timing_estimate", {}).get("estimated_duration_seconds", 0)
                message["voice_path"] = str(local_path)
                message["voice_duration_seconds"] = duration
                message["voice_status"] = "completed"
                self.persistence.save_stage_output("d", message, clean_title, chunk_label, scene_id)
                self.tracker.mark_as_completed(book_id, unique_aria_job_id, str(local_path))
                return message

            # === STEP 2: CHECK REMOTO (ARIA PC 139) ===
            aria_host = os.getenv("ARIA_HOST", "192.168.1.139")
            aria_asset_port = os.getenv("ARIA_ASSET_PORT", "8082")
            expected_url = f"http://{aria_host}:{aria_asset_port}/{unique_aria_job_id}.wav"
            
            self.logger.info(f"Checking for remote asset existence: {expected_url}")
            try:
                head_resp = requests.head(expected_url, timeout=5)
                if head_resp.status_code == 200:
                    self.logger.info(f"🌐 Remote Hit! Scena {unique_aria_job_id} trovata su ARIA. Scarico direttamente ignorando TTS...")
                    if self._download_file(expected_url, local_path):
                        self.logger.info(f"✅ Download completato dal Remote.")
                        duration = message.get("timing_estimate", {}).get("estimated_duration_seconds", 0)
                        message["voice_path"] = str(local_path)
                        message["voice_duration_seconds"] = duration
                        message["voice_status"] = "completed"
                        self.persistence.save_stage_output("d", message, clean_title, chunk_label, scene_id)
                        self.tracker.mark_as_completed(book_id, unique_aria_job_id, str(local_path))
                        return message
                    else:
                        self.logger.warning("Download fallito nonostante il file remoto esista. Procedo alla generazione...")
            except Exception as e:
                self.logger.warning(f"Remote check fallito per {expected_url}: {e}")

            # === STEP 3: GENERAZIONE EFFETTIVA (ARIA TTS) ===
            text_to_speak = message.get("fish_annotated_text") or message.get("text_content")
            
            # Parametri dinamici
            temp = 0.7
            top_p = 0.8
            if getattr(self, "enable_dynamic_params", False):
                voice_dir = message.get("voice_direction", {})
                tension = voice_dir.get("energy", 0.5)
                temp = 0.6 + (tension * 0.2)
            
            callback_key = f"dias:callback:stage_d:{job_id}:{scene_id}"

            # Configurazione Backend Dinamica
            target_model = message.get("tts_model_id") or message.get("tts_backend") or self.config.models.active_tts_backend
            
            backend_cfg = None
            if "qwen3" in target_model.lower():
                backend_cfg = self.config.models.qwen3_tts
            elif "fish" in target_model.lower():
                backend_cfg = self.config.models.fish_s1_mini
            
            if backend_cfg:
                default_voice = backend_cfg.default_voice
                default_instruct = backend_cfg.default_instruct
                default_temp = backend_cfg.default_temperature
                default_top_p = backend_cfg.default_top_p
            else:
                default_voice = "luca"
                default_instruct = "Professional Italian narrator."
                default_temp = 0.5
                default_top_p = 0.9

            # Override da messaggio (Stage C) o da Config
            instruct = message.get("qwen3_instruct") or default_instruct
            voice_id = message.get("voice_id") or default_voice
            temp = message.get("temperature") or temp or default_temp
            top_p = message.get("top_p") or default_top_p
            
            # Voice Safety Check (Prevent 'aura' hallucinations and ensure Qwen3 compatibility)
            if "qwen3" in target_model.lower():
                valid_qwen3_voices = ["luca", "narratore"]
                if voice_id.lower() == "aura":
                    self.logger.warning(f"Identificato voice_id 'aura'. Sostituisco col default '{default_voice}'.")
                    voice_id = default_voice
            
            # New Standard: aria:q:local:tts:{model}:{client}
            self.aria_tts_queue = f"aria:q:local:tts:{target_model}:dias"
            
            aria_task = {
                "job_id": unique_aria_job_id,
                "client_id": "dias",
                "model_type": "tts",
                "model_id": target_model,
                "payload": {
                    "job_id": unique_aria_job_id,
                    "text": text_to_speak,
                    "voice_id": voice_id,
                    "instruct": instruct,
                    "temperature": temp,
                    "top_p": top_p,
                    "output_format": "wav"
                },
                "callback_key": callback_key,
                "timeout_seconds": 600
            }
            
            self.logger.info(f"Sottomissione TASK REALE ad ARIA per scena {unique_aria_job_id}")
            self.redis.push_to_queue(self.aria_tts_queue, aria_task)
            
            # === STEP 4: ATTESA CALLBACK ===
            self.logger.info(f"In attesa di callback su {callback_key} (timeout 900s)...")
            result_raw = self.redis.consume_from_queue(callback_key, timeout=900)
            
            if not result_raw:
                error_msg = f"Timeout attesa risultato ARIA per scena {unique_aria_job_id}"
                self.logger.error(error_msg)
                return None
                
            aria_result = result_raw if isinstance(result_raw, dict) else json.loads(result_raw)
            if aria_result.get("status") != "done":
                error_msg = f"Errore ARIA: {aria_result.get('error')}"
                self.logger.error(error_msg)
                return None
            
            final_url = aria_result.get("output", {}).get("audio_url")
            duration = aria_result.get("output", {}).get("duration_seconds")
            self.logger.info(f"Scena {unique_aria_job_id} generata con successo: {final_url}")
            
            # --- LOCAL SYNC ---
            if self._download_file(final_url, local_path):
                self.logger.info(f"✅ Asset sincronizzato in locale: {local_path}")
                final_path_for_registry = str(local_path)
            else:
                self.logger.warning(f"❌ Sincronizzazione fallita per {final_url}. Uso URL remoto come fallback.")
                final_path_for_registry = final_url

            # === STEP 5: REGISTRAZIONE COMPLETAMENTO ===
            self.tracker.mark_as_completed(book_id, unique_aria_job_id, final_path_for_registry)
            entry = self.tracker.get_entry(book_id, unique_aria_job_id)
            if entry:
                entry.metadata["duration_seconds"] = duration
                self.tracker.set_entry(book_id, entry)

            message["voice_path"] = final_path_for_registry
            message["voice_duration_seconds"] = duration
            message["voice_status"] = "completed"
            
            self.persistence.save_stage_output("d", message, clean_title, chunk_label, scene_id)
            return message
            
        except Exception as e:
            self.logger.error(f"Errore nello Stage D Proxy: {e}", exc_info=True)
            return None

    def _download_file(self, url: str, dest_path: Path) -> bool:
        """
        Scarica un file via HTTP con retry basico.
        """
        for attempt in range(3):
            try:
                response = requests.get(url, timeout=30, stream=True)
                if response.status_code == 200:
                    with open(dest_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
                else:
                    self.logger.error(f"Download failed with status {response.status_code} for {url}")
            except Exception as e:
                self.logger.error(f"Attempt {attempt+1} failed for {url}: {e}")
                time.sleep(2)
        return False

if __name__ == "__main__":
    stage = StageDVoiceGeneratorProxy()
    stage.run()
