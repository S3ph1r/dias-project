"""
DIAS Base Stage

Classe base astratta per tutti i 7 stadi della pipeline.
Gestisce: consume queue → process → produce next queue → checkpoint.
Include signal handling per graceful shutdown.
"""

import signal
import sys
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .config import get_config, DiasConfig
from .redis_client import DiasRedis
from .logging_setup import setup_logging


class BaseStage(ABC):
    """
    Classe base per tutti gli stadi DIAS.

    Per creare un nuovo stadio:

        class MyStage(BaseStage):
            def process(self, message: dict) -> Optional[dict]:
                # La tua logica qui
                return result_dict  # o None per non produrre output

    Poi:

        cfg = get_config() # Ottieni la configurazione
        stage = MyStage(
            stage_name="stage_a",
            stage_number=1,
            input_queue=cfg.queues.ingestion,
            output_queue=cfg.queues.semantic,
        )
        stage.run()
    """

    def __init__(
        self,
        stage_name: str,
        stage_number: int,
        input_queue: Optional[str] = None,
        output_queue: Optional[str] = None,
        config: Optional[DiasConfig] = None,
        redis_client: Optional[DiasRedis] = None,
    ):
        """
        Args:
            stage_name: Nome identificativo (es. "stage_a", "stage_b")
            stage_number: Numero dello stadio (1-7)
            input_queue: Nome coda Redis da consumare
            output_queue: Nome coda Redis per output (None se ultimo stadio)
            config: Configurazione DIAS (se None, carica da file)
            redis_client: Client Redis (se None, crea da config)
        """
        self.stage_name = stage_name
        self.stage_number = stage_number
        self.input_queue = input_queue
        self.output_queue = output_queue

        # Config
        self.config = config or get_config()

        # Logging
        self.logger = setup_logging(
            stage_name,
            level=self.config.logging.level,
            log_file=self.config.logging.file,
        )

        # Redis
        if redis_client is not None:
            self.redis = redis_client
        else:
            self.redis = DiasRedis(
                host=self.config.redis.host,
                port=self.config.redis.port,
                db=self.config.redis.db,
                decode_responses=self.config.redis.decode_responses,
                retry_attempts=self.config.redis.retry_attempts,
                retry_backoff_base=self.config.redis.retry_backoff_base,
            )

        # Graceful shutdown
        self._running = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Registra handler per SIGTERM e SIGINT → graceful shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name}, shutting down gracefully...")
        self._running = False

    # --- Abstract methods ---

    @abstractmethod
    def process(self, message: dict) -> Optional[dict]:
        """
        Processa un messaggio dalla coda di input.

        Args:
            message: Messaggio deserializzato dalla coda Redis.

        Returns:
            Dizionario da inviare alla coda successiva, o None
            se questo stadio non produce output per questo messaggio.

        Raises:
            Exception: Qualsiasi errore viene gestito dal run loop.
        """
        ...

    # --- Lifecycle hooks (overridabili) ---

    def on_start(self) -> None:
        """Chiamato una volta all'avvio del run loop. Override per setup."""
        pass

    def on_stop(self) -> None:
        """Chiamato alla fine del run loop. Override per cleanup."""
        pass

    def on_error(self, error: Exception, message: dict) -> bool:
        """
        Chiamato quando process() solleva un'eccezione.

        Args:
            error: L'eccezione sollevata
            message: Il messaggio che ha causato l'errore

        Returns:
            True per continuare il loop, False per fermarsi.
        """
        self.logger.error(
            f"Error processing message: {error}",
            exc_info=True,
            extra={"book_id": message.get("book_id", "unknown")},
        )
        return True  # Default: continua

    # --- Run loop ---

    def run(self, consume_timeout: int = 5) -> None:
        """
        Loop principale dello stadio.

        1. Health check Redis
        2. Consume da input_queue (BRPOP)
        3. Chiama process(message)
        4. Se result: push su output_queue
        5. Checkpoint
        6. Ripeti fino a shutdown

        Args:
            consume_timeout: Secondi di attesa su BRPOP prima di riprovare.
                            Più basso = più reattivo allo shutdown.
        """
        self.logger.info(f"Starting {self.stage_name} (stage {self.stage_number})")

        # Health check
        if not self.redis.health_check():
            self.logger.error("Redis health check failed, cannot start")
            sys.exit(1)

        self._running = True
        self.on_start()

        self.logger.info(
            f"Listening on queue: {self.input_queue}"
            + (f" → {self.output_queue}" if self.output_queue else "")
        )

        try:
            while self._running:
                # Consume (con timeout per poter controllare _running)
                message = self.redis.consume_from_queue(
                    self.input_queue, timeout=consume_timeout
                )

                if message is None:
                    continue  # Timeout, ricontrolla _running

                book_id = message.get("book_id", "unknown")
                self.logger.info(
                    f"Processing message for book={book_id}",
                    extra={"book_id": book_id},
                )

                try:
                    result = self.process(message)

                    # Produce output only if success
                    if result is not None:
                        if self.output_queue:
                            self.redis.push_to_queue(self.output_queue, result)

                        # Checkpoint only on SUCCESSful processing
                        if book_id != "unknown":
                            self.redis.set_checkpoint(book_id, self.stage_number)

                        self.logger.info(
                            f"Completed message for book={book_id}",
                            extra={"book_id": book_id},
                        )
                    else:
                        self.logger.info(f"Process returned None for book={book_id} (No output/Skipped)")

                except Exception as e:
                    # IMPLEMENTAZIONE CATENA SEQUENZIALE RIGOROSA (v2.0)
                    error_msg = str(e)
                    self.logger.error(f"❌ Errore critico in {self.stage_name}: {error_msg}")
                    
                    # 1. Rimetti il messaggio in TESTA alla coda (RPUSH su BRPOP queue)
                    self.logger.info(f"🔄 Re-enqueueing task for book={book_id} to the HEAD of {self.input_queue}")
                    self.redis.push_to_head(self.input_queue, message)
                    
                    # 2. Imposta il flag di PAUSA GLOBALE in Redis
                    pause_key = "dias:status:paused"
                    pause_reason = f"Stage {self.stage_name} (Number {self.stage_number}) failed: {error_msg}"
                    self.redis.set(pause_key, pause_reason)
                    self.logger.critical(f"🛑 GLOBAL PAUSE SET: {pause_reason}")
                    
                    # 3. Shutdown immediato dello stadio
                    self._running = False
                    if not self.on_error(e, message):
                        break
                    
                    # Forza l'uscita del processo per essere certi che l'orchestratore lo rilevi
                    sys.exit(1)

        finally:
            self.on_stop()
            self.logger.info(f"Stopped {self.stage_name}")

    def shutdown(self) -> None:
        """Richiede graceful shutdown del loop."""
        self._running = False
