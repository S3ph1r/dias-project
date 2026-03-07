"""
DIAS Master Registry
Gestisce lo stato dei task (Scene, Musica, etc.) per garantire l'idempotenza
e la resilienza della pipeline distribuita.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .redis_client import DiasRedis
from .models import RegistryEntry, TaskStatus
from .logging_setup import get_logger

class ActiveTaskTracker:
    """
    Tracker per i task "in volo" nella pipeline DIAS.
    Utilizza Redis Hash per mantenere lo stato di ogni task.
    """

    def __init__(self, redis_client: DiasRedis, logger: Optional[logging.Logger] = None):
        self.redis = redis_client
        self.logger = logger or get_logger("task_tracker")
        self.zombie_timeout = timedelta(minutes=30) # Default timeout per task zombie

    def _get_registry_key(self, book_id: str) -> str:
        return f"dias:registry:{book_id}"

    def get_entry(self, book_id: str, task_id: str) -> Optional[RegistryEntry]:
        """Recupera l'entry del registro per un task specifico."""
        raw = self.redis.get_state(self._get_registry_key(book_id), task_id)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return RegistryEntry(**data)
        except Exception as e:
            self.logger.error(f"Errore nel parsing del registro per {task_id}: {e}")
            return None

    def set_entry(self, book_id: str, entry: RegistryEntry) -> None:
        """Salva o aggiorna un'entry nel registro."""
        entry.updated_at = datetime.now(timezone.utc)
        raw = entry.model_dump_json()
        self.redis.set_state(self._get_registry_key(book_id), entry.task_id, raw)

    def is_task_ready_to_send(self, book_id: str, task_id: str) -> bool:
        """
        Determina se un task può essere inviato ad ARIA.
        Ritorna True se:
        - Non esiste nel registro.
        - Esiste ma è in stato PENDING, FAILED o TIMEOUT.
        - Esiste in stato IN_FLIGHT ma è diventato uno "Zombie" (timeout superato).
        """
        entry = self.get_entry(book_id, task_id)
        
        if not entry:
            return True
            
        if entry.status in [TaskStatus.COMPLETED]:
            return False
            
        if entry.status in [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
            return True
            
        if entry.status == TaskStatus.IN_FLIGHT:
            # Verifica se è uno zombie
            elapsed = datetime.now(timezone.utc) - entry.updated_at
            if elapsed > self.zombie_timeout:
                self.logger.warning(f"Task {task_id} rilevato come ZOMBIE (in volo da {elapsed})")
                entry.status = TaskStatus.TIMEOUT
                entry.error = f"Zombie task: timeout di {self.zombie_timeout} superato"
                self.set_entry(book_id, entry)
                return True
            return False
            
        return False

    def mark_as_inflight(self, book_id: str, task_id: str, callback_key: str, worker_id: Optional[str] = None) -> None:
        """Marca un task come inviato e in attesa di risposta."""
        entry = self.get_entry(book_id, task_id)
        if not entry:
            entry = RegistryEntry(task_id=task_id, status=TaskStatus.IN_FLIGHT)
        else:
            entry.status = TaskStatus.IN_FLIGHT
            entry.attempts += 1
            
        entry.callback_key = callback_key
        entry.worker_id = worker_id
        entry.error = None
        self.set_entry(book_id, entry)

    def mark_as_completed(self, book_id: str, task_id: str, output_path: str) -> None:
        """Marca un task come completato con successo."""
        entry = self.get_entry(book_id, task_id)
        if not entry:
            entry = RegistryEntry(task_id=task_id, status=TaskStatus.COMPLETED)
        else:
            entry.status = TaskStatus.COMPLETED
            
        entry.output_path = output_path
        entry.error = None
        self.set_entry(book_id, entry)

    def mark_as_failed(self, book_id: str, task_id: str, error: str) -> None:
        """Marca un task come fallito."""
        entry = self.get_entry(book_id, task_id)
        if not entry:
            entry = RegistryEntry(task_id=task_id, status=TaskStatus.FAILED)
        else:
            entry.status = TaskStatus.FAILED
            
        entry.error = error
        self.set_entry(book_id, entry)

    def get_all_entries(self, book_id: str) -> List[RegistryEntry]:
        """Ritorna tutti i task registrati per un libro."""
        all_raw = self.redis.get_state(self._get_registry_key(book_id))
        entries = []
        if not all_raw:
            return entries
            
        for task_id, raw in all_raw.items():
            try:
                data = json.loads(raw)
                entries.append(RegistryEntry(**data))
            except:
                continue
        return sorted(entries, key=lambda x: x.task_id)
