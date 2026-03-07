import sys
from pathlib import Path
import unittest
from datetime import datetime, timezone, timedelta
import json

# Aggiungi src al path
sys.path.append(str(Path(__file__).parent.parent))

from src.common.registry import ActiveTaskTracker, TaskStatus
from src.common.mock_redis import MockRedisClient

class TestActiveTaskTracker(unittest.TestCase):
    def setUp(self):
        self.mock_redis_client = MockRedisClient().get_client()
        # Wrapper per DiasRedis mockato (MockRedisClient ritorna un redis.Redis mock, non DiasRedis)
        # Ma ActiveTaskTracker si aspetta DiasRedis. 
        # Per test semplici, iniettiamo un oggetto che mima DiasRedis
        class MockDiasRedis:
            def __init__(self, client): self._client = client
            def set_state(self, k, f, v): self._client.hset(k, f, v)
            def get_state(self, k, f=None): 
                if f is None: return self._client.hgetall(k)
                return self._client.hget(k, f)
        
        self.dias_redis = MockDiasRedis(self.mock_redis_client)
        self.tracker = ActiveTaskTracker(self.dias_redis)

    def test_flow_normale(self):
        book_id = "test-book"
        task_id = "scene-01"
        
        # 1. Inizialmente pronto
        self.assertTrue(self.tracker.is_task_ready_to_send(book_id, task_id))
        
        # 2. Marca come in volo
        self.tracker.mark_as_inflight(book_id, task_id, "callback-01")
        self.assertFalse(self.tracker.is_task_ready_to_send(book_id, task_id))
        
        # 3. Verifica stato
        entry = self.tracker.get_entry(book_id, task_id)
        self.assertEqual(entry.status, TaskStatus.IN_FLIGHT)
        self.assertEqual(entry.callback_key, "callback-01")
        
        # 4. Marca come completato
        self.tracker.mark_as_completed(book_id, task_id, "/path/to/audio.wav")
        self.assertFalse(self.tracker.is_task_ready_to_send(book_id, task_id))
        
        entry = self.tracker.get_entry(book_id, task_id)
        self.assertEqual(entry.status, TaskStatus.COMPLETED)
        self.assertEqual(entry.output_path, "/path/to/audio.wav")

    def test_zombie_detection(self):
        book_id = "test-book"
        task_id = "scene-zombie"
        
        # Marca come in volo con data passata
        entry = self.tracker.get_entry(book_id, task_id)
        if not entry:
            from src.common.models import RegistryEntry
            entry = RegistryEntry(task_id=task_id, status=TaskStatus.IN_FLIGHT)
        
        # Trucco per forzare una data vecchia nel registro
        entry.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        # Usiamo direttamente redis per evitare che tracker.set_entry aggiorni il timestamp
        self.dias_redis.set_state(self.tracker._get_registry_key(book_id), task_id, entry.model_dump_json())
        
        # Dovrebbe essere rilevato come zombie e quindi pronto al rinvio
        self.assertTrue(self.tracker.is_task_ready_to_send(book_id, task_id))
        
        entry = self.tracker.get_entry(book_id, task_id)
        self.assertEqual(entry.status, TaskStatus.TIMEOUT)

if __name__ == '__main__':
    unittest.main()
