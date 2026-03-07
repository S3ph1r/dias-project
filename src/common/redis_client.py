"""
DIAS Redis Client

Wrapper su redis.Redis con:
- Queue helpers (push/consume con serializzazione JSON)
- Checkpoint management
- Distributed locking
- Rate limiting per API
- Retry automatico su ConnectionError
- Health check
"""

import json
import time
import logging
import os
from typing import Any, Optional

import redis

from .logging_setup import get_logger


class DiasRedis:
    """Client Redis wrapper per DIAS pipeline."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = None,
        decode_responses: bool = None,
        retry_attempts: int = None,
        retry_backoff_base: float = None,
        client: Optional[redis.Redis] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            client: Client Redis iniettato (per testing con fakeredis).
                    Se fornito, gli altri parametri vengono ignorati.
            logger: Optional logger for debugging
        """
        # Use environment variables as defaults if not provided
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', '6379'))
        self.db = db or int(os.getenv('REDIS_DB', '0'))
        self.decode_responses = decode_responses if decode_responses is not None else True
        self.retry_attempts = retry_attempts or int(os.getenv('REDIS_RETRY_ATTEMPTS', '3'))
        self.retry_backoff_base = retry_backoff_base or float(os.getenv('REDIS_RETRY_BACKOFF', '1.0'))
        
        # Use provided logger or create default
        self.logger = logger or get_logger("redis_client")
        self.logger = get_logger("redis_client")

        if client is not None:
            self._client = client
        else:
            self.logger.info(f"Connecting to Redis at {self.host}:{self.port}")
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=self.decode_responses,
                socket_connect_timeout=5,
                socket_timeout=360,
            )

        self._retry_attempts = self.retry_attempts
        self._retry_backoff_base = self.retry_backoff_base

    @property
    def client(self) -> redis.Redis:
        """Accesso diretto al client Redis."""
        return self._client

    def _retry(self, fn, *args, **kwargs):
        """Esegue fn con retry su ConnectionError."""
        last_error = None
        for attempt in range(self._retry_attempts):
            try:
                return fn(*args, **kwargs)
            except (redis.ConnectionError, redis.TimeoutError) as e:
                last_error = e
                wait = self._retry_backoff_base * (2 ** attempt)
                self.logger.warning(
                    f"Redis connection error (attempt {attempt + 1}/{self._retry_attempts}), "
                    f"retrying in {wait:.1f}s: {e}"
                )
                time.sleep(wait)
        raise last_error

    # --- Health ---

    def health_check(self) -> bool:
        """Verifica che Redis risponda a PING."""
        try:
            return self._retry(self._client.ping)
        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False

    # --- Queue Operations ---

    def push_to_queue(self, queue_name: str, message: dict) -> int:
        """
        Inserisce un messaggio nella coda (LPUSH).
        Il messaggio viene serializzato in JSON.

        Returns:
            Lunghezza della coda dopo l'inserimento.
        """
        payload = json.dumps(message, ensure_ascii=False)
        result = self._retry(self._client.lpush, queue_name, payload)
        self.logger.debug(f"Pushed to {queue_name}, queue length: {result}")
        return result

    def consume_from_queue(
        self, queue_name: str, timeout: int = 0
    ) -> Optional[dict]:
        """
        Consuma un messaggio dalla coda (BRPOP).

        Args:
            queue_name: Nome della coda Redis.
            timeout: Secondi di attesa (0 = infinito).

        Returns:
            Messaggio deserializzato, o None se timeout raggiunto.
        """
        result = self._retry(self._client.brpop, queue_name, timeout=timeout)
        if result is None:
            return None

        _, raw = result
        message = json.loads(raw)
        self.logger.debug(f"Consumed from {queue_name}")
        return message

    def queue_length(self, queue_name: str) -> int:
        """Ritorna il numero di messaggi in coda."""
        return self._retry(self._client.llen, queue_name)

    # --- Checkpoint ---

    def set_checkpoint(self, book_id: str, stage: int) -> None:
        """Salva checkpoint: ultimo stadio completato per un libro."""
        key = f"dias:checkpoint:{book_id}"
        self._retry(self._client.set, key, str(stage))
        self.logger.info(
            f"Checkpoint set: book={book_id}, stage={stage}",
        )

    def get_checkpoint(self, book_id: str) -> Optional[int]:
        """Recupera ultimo stadio completato. None se nessun checkpoint."""
        key = f"dias:checkpoint:{book_id}"
        value = self._retry(self._client.get, key)
        return int(value) if value is not None else None

    # --- State Management ---

    def set_state(self, key: str, field: str, value: str) -> None:
        """Scrive un campo in un hash di stato (HSET)."""
        self._retry(self._client.hset, key, field, value)

    def get_state(self, key: str, field: Optional[str] = None) -> Any:
        """
        Legge stato.
        Se field è None, ritorna tutto l'hash (HGETALL).
        Altrimenti ritorna il singolo campo (HGET).
        """
        if field is None:
            return self._retry(self._client.hgetall, key)
        return self._retry(self._client.hget, key, field)

    # --- Distributed Locking ---

    def acquire_lock(self, name: str, ttl: int = 30) -> bool:
        """
        Acquisisce un lock distribuito con TTL.

        Args:
            name: Nome del lock (es. "api:google_gemini")
            ttl: Time-to-live in secondi

        Returns:
            True se il lock è stato acquisito, False se già occupato.
        """
        key = f"dias:lock:{name}"
        acquired = self._retry(self._client.set, key, "1", nx=True, ex=ttl)
        if acquired:
            self.logger.debug(f"Lock acquired: {name} (TTL={ttl}s)")
        return bool(acquired)

    def release_lock(self, name: str) -> None:
        """Rilascia un lock distribuito."""
        key = f"dias:lock:{name}"
        self._retry(self._client.delete, key)
        self.logger.debug(f"Lock released: {name}")

    # --- Rate Limiting ---

    def set_throttle(self, name: str) -> None:
        """Registra il timestamp corrente per rate limiting."""
        key = f"dias:throttle:{name}"
        self._retry(self._client.set, key, str(time.time()))

    def get_throttle(self, name: str) -> Optional[float]:
        """Ritorna il timestamp dell'ultima chiamata. None se mai chiamata."""
        key = f"dias:throttle:{name}"
        value = self._retry(self._client.get, key)
        return float(value) if value is not None else None

    def wait_for_throttle(self, name: str, min_interval: float) -> None:
        """
        Attende se necessario per rispettare il rate limit.

        Args:
            name: Nome del throttle (es. "api:google")
            min_interval: Secondi minimi tra chiamate
        """
        last = self.get_throttle(name)
        if last is not None:
            elapsed = time.time() - last
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                self.logger.info(
                    f"Rate limiting: waiting {wait_time:.1f}s for {name}"
                )
                time.sleep(wait_time)
