"""
Rate limiter per Google Gemini API - 1 richiesta ogni 5 minuti
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Optional
import logging


class GeminiRateLimiter:
    """
    Implementa rate limiting per Gemini API:
    - Minimo 30 secondi tra le richieste.
    - Lockout di 10 minuti in caso di errore 429.
    """
    
    def __init__(self, min_delay_seconds: int = 30, lockout_minutes: int = 1440):
        self.min_delay = timedelta(seconds=min_delay_seconds)
        self.lockout_duration = timedelta(minutes=lockout_minutes)
        self.last_request_time: Optional[datetime] = None
        self.lockout_until: Optional[datetime] = None
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        
    def report_429(self):
        """Segnala un errore 429 e attiva il lockout"""
        with self.lock:
            self.lockout_until = datetime.now() + self.lockout_duration
            self.logger.warning(f"⚠️ Errore 429 rilevato! Lockout attivato fino a {self.lockout_until.isoformat()}")

    def can_make_request(self) -> bool:
        """Verifica se possiamo fare una richiesta ora"""
        with self.lock:
            now = datetime.now()
            
            # Check lockout
            if self.lockout_until and now < self.lockout_until:
                return False
                
            # Check min delay
            if self.last_request_time and (now - self.last_request_time) < self.min_delay:
                return False
                
            return True
    
    def wait_for_slot(self) -> float:
        """Aspetta finché non c'è uno slot disponibile"""
        total_wait_time = 0.0
        
        while True:
            with self.lock:
                now = datetime.now()
                
                # 1. Handle lockout
                if self.lockout_until and now < self.lockout_until:
                    wait_seconds = (self.lockout_until - now).total_seconds()
                    self.logger.warning(f"🚫 Lockout 429 attivo. Attesa di {wait_seconds:.1f}s...")
                # 2. Handle min delay
                elif self.last_request_time and (now - self.last_request_time) < self.min_delay:
                    wait_seconds = (self.last_request_time + self.min_delay - now).total_seconds()
                    # self.logger.debug(f"Pacing: attesa {wait_seconds:.1f}s...")
                else:
                    # Slot disponibile!
                    self.last_request_time = now
                    return total_wait_time

            # Dormi fuori dal lock
            time.sleep(wait_seconds)
            total_wait_time += wait_seconds
    
    def get_status(self) -> dict:
        """Ritorna stato corrente del rate limiter"""
        with self.lock:
            now = datetime.now()
            is_locked = self.lockout_until and now < self.lockout_until
            
            return {
                "is_locked": is_locked,
                "lockout_until": self.lockout_until.isoformat() if self.lockout_until else None,
                "last_request": self.last_request_time.isoformat() if self.last_request_time else None,
                "can_make_request": self.can_make_request()
            }
    
    def reset(self):
        """Resetta il rate limiter"""
        with self.lock:
            self.last_request_time = None
            self.lockout_until = None
            self.logger.info("Rate limiter resettato")


# Global rate limiter instance (30s delay, 10m lockout on 429)
gemini_rate_limiter = GeminiRateLimiter(min_delay_seconds=30, lockout_minutes=1440)