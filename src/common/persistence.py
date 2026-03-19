"""
DIAS Persistence Manager - Gestione salvataggio su disco
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import logging


class DateTimeEncoder(json.JSONEncoder):
    """Serializzatore JSON personalizzato per datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class DiasPersistence:
    """Gestore persistenza file-based per DIAS"""
    
    def __init__(self, base_path: Optional[str] = None):
        if base_path:
            self.base_path = Path(base_path)
        else:
            # 1. Cerca variabile d'ambiente
            env_path = os.environ.get("DIAS_DATA_DIR")
            if env_path:
                self.base_path = Path(env_path)
            else:
                # 2. Default basato sulla posizione del file (root del progetto /data)
                self.base_path = Path(__file__).parent.parent.parent / "data"
        
        self.logger = logging.getLogger(__name__)
        
        # Crea struttura directory se non esiste
        self._ensure_directories()

    @staticmethod
    def normalize_id(text: str) -> str:
        """
        Normalizza un titolo o ID per l'uso coerente nei nomi dei file.
        Esempio: "Cronache del Silicio" -> "Cronache-del-Silicio"
        """
        if not text:
            return "unknown"
        # Sostituisce spazi e caratteri non alfanumerici con hyphens
        normalized = "".join([c if c.isalnum() else "-" for c in text])
        # Rimuove hyphens duplicati e pulisce estremità
        import re
        normalized = re.sub(r'-+', '-', normalized).strip("-")
        return normalized

    def _ensure_directories(self):
        """Assicura che tutte le directory esistano"""
        dirs = [
            "stage_a/input", "stage_a/output",
            "stage_b/input", "stage_b/output", 
            "stage_c/input", "stage_c/output",
            "stage_d/input", "stage_d/output",
            "final", "logs"
        ]
        
        for dir_name in dirs:
            path = self.base_path / dir_name
            path.mkdir(parents=True, exist_ok=True)
    
    def save_stage_input(self, stage: str, data: Dict[str, Any], book_id: str, 
                        block_id: Optional[str] = None) -> str:
        """Salva input di uno stage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        components = [book_id]
        if block_id:
            components.append(block_id)
        
        filename = "-".join(components) + f"-{timestamp}.json"
        
        filepath = self.base_path / f"stage_{stage}" / "input" / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            self.logger.info(f"✅ Salvato input Stage {stage}: {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Errore salvataggio input Stage {stage}: {e}")
            raise
    
    def save_stage_output(self, stage: str, data: Dict[str, Any], book_id: str,
                         block_id: Optional[str] = None,
                         scene_id: Optional[str] = None,
                         custom_filename: Optional[str] = None) -> str:
        """Salva output di uno stage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Coherence: Force normalization on book_id (which is our project title)
        book_id = self.normalize_id(book_id)
        
        components = [book_id]
        if block_id:
            components.append(block_id)
        if scene_id:
            components.append(scene_id)
        if custom_filename:
            components.append(custom_filename)
        
        filename = "-".join(components) + f"-{timestamp}.json"
        
        filepath = self.base_path / f"stage_{stage}" / "output" / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            self.logger.info(f"✅ Salvato output Stage {stage} (Coerenza): {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Errore salvataggio output Stage {stage}: {e}")
            raise
    
    def load_stage_input(self, stage: str, filepath: str) -> Dict[str, Any]:
        """Carica input di uno stage"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            self.logger.error(f"❌ Errore caricamento input Stage {stage}: {e}")
            raise
    
    def load_stage_output(self, stage: str, book_id: str, 
                         block_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Carica l'ultimo output di uno stage per book_id e block_id"""
        output_dir = self.base_path / f"stage_{stage}" / "output"
        
        if block_id:
            pattern = f"{book_id}-{block_id}-*.json"
        else:
            pattern = f"{book_id}-*.json"
        
        files = list(output_dir.glob(pattern))
        
        if not files:
            self.logger.warning(f"⚠️ Nessun output trovato per {book_id}_{block_id}")
            return None
        
        # Prendi il file più recente
        latest_file = max(files, key=lambda x: x.stat().st_mtime)
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            self.logger.error(f"❌ Errore caricamento output da {latest_file}: {e}")
            raise
    
    def save_final_output(self, data: Dict[str, Any], book_id: str) -> str:
        """Salva output finale"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{book_id}_final_{timestamp}.json"
        filepath = self.base_path / "final" / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ Salvato output finale: {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Errore salvataggio output finale: {e}")
            raise
    
    def get_processing_status(self, book_id: str) -> Dict[str, Any]:
        """Ottieni stato processing per un libro"""
        status = {
            "book_id": book_id,
            "stage_a_input": 0,
            "stage_a_output": 0,
            "stage_b_output": 0,
            "stage_c_output": 0,
            "final_output": 0,
            "total_blocks": 0,
            "completed_blocks": 0
        }
        
        # Conta file per ogni stage
        for stage in ['a', 'b', 'c']:
            input_dir = self.base_path / f"stage_{stage}" / "input"
            output_dir = self.base_path / f"stage_{stage}" / "output"
            
            if input_dir.exists():
                status[f"stage_{stage}_input"] = len(list(input_dir.glob(f"{book_id}-*.json")))
            
            if output_dir.exists():
                status[f"stage_{stage}_output"] = len(list(output_dir.glob(f"{book_id}-*.json")))
        
        # Conta output finali
        final_dir = self.base_path / "final"
        if final_dir.exists():
            status["final_output"] = len(list(final_dir.glob(f"{book_id}_*.json")))
        
        # Calcola totali
        status["total_blocks"] = status["stage_a_input"]
        status["completed_blocks"] = status["stage_c_output"]
        
        return status
    
    def cleanup_stage(self, stage: str, book_id: str):
        """Pulisce file temporanei di uno stage (da chiamare alla fine)"""
        self.logger.info(f"🧹 Pulizia Stage {stage} per {book_id}")
        
        for subdir in ['input', 'output']:
            dir_path = self.base_path / f"stage_{stage}" / subdir
            if dir_path.exists():
                files = list(dir_path.glob(f"{book_id}-*.json"))
                for file in files:
                    try:
                        file.unlink()
                        self.logger.debug(f"🗑️ Eliminato: {file}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Impossibile eliminare {file}: {e}")
    
    def cleanup_all(self, book_id: str):
        """Pulisce tutti i file temporanei (da chiamare alla fine)"""
        self.logger.info(f"🧹 Pulizia completa per {book_id}")
        
        for stage in ['a', 'b', 'c']:
            self.cleanup_stage(stage, book_id)