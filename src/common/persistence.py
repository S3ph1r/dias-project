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
    """Gestore persistenza file-based per DIAS con supporto multi-progetto"""
    
    def __init__(self, base_path: Optional[str] = None, project_id: Optional[str] = None):
        if base_path:
            self.base_path = Path(base_path)
        else:
            env_path = os.environ.get("DIAS_DATA_DIR")
            if env_path:
                self.base_path = Path(env_path)
            else:
                self.base_path = Path(__file__).parent.parent.parent / "data"
        
        self.project_id = project_id
        if self.project_id:
            # Nuova struttura: data/projects/{project_id}/
            self.project_root = self.base_path / "projects" / self.project_id
        else:
            # Struttura legacy: data/
            self.project_root = self.base_path

        self.logger = logging.getLogger(__name__)
        self._ensure_directories()

    def get_fingerprint_path(self) -> Path:
        """Restituisce il path standard per il file Intelligence (fingerprint.json)"""
        if self.project_id:
            # Stage 0 output directory mapping
            return self.project_root / "stages" / "stage_0" / "output" / "fingerprint.json"
        return self.base_path / "fingerprint.json"

    def get_preproduction_path(self) -> Path:
        """Restituisce il path standard per il dossier di pre-produzione (casting, etc.)"""
        if self.project_id:
            return self.project_root / "stages" / "stage_0" / "output" / "preproduction.json"
        return self.base_path / "preproduction.json"

    def get_source_text_path(self) -> Optional[Path]:
        """Trova il file .txt sorgente nella cartella source/ del progetto"""
        if not self.project_id:
            return None
        source_dir = self.project_root / "source"
        if not source_dir.exists():
            return None
        # Cerca il primo file .txt
        txt_files = list(source_dir.glob("*.txt"))
        return txt_files[0] if txt_files else None

    def get_normalized_text_path(self) -> Optional[Path]:
        """Trova il file .txt normalizzato nella cartella stage_0/output/"""
        if not self.project_id:
            return None
        output_dir = self.project_root / "stages" / "stage_0" / "output"
        if not output_dir.exists():
            return None
        # Cerca i file .txt (dovrebbe essercene solo uno)
        txt_files = list(output_dir.glob("*.txt"))
        return txt_files[0] if txt_files else None

    def load_config(self) -> Dict[str, Any]:
        """Carica il file config.json del progetto"""
        if not self.project_id:
            return {}
        config_path = self.project_root / "config.json"
        if not config_path.exists():
            return {}
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Errore caricamento config: {e}")
            return {}

    def save_config(self, config: Dict[str, Any]):
        """Salva il file config.json del progetto"""
        if not self.project_id:
            return
        config_path = self.project_root / "config.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Errore salvataggio config: {e}")

    def update_project_config(self, updates: Dict[str, Any]):
        """Aggiorna chiavi specifiche nel config.json"""
        config = self.load_config()
        config.update(updates)
        self.save_config(config)

    @staticmethod
    def normalize_id(text: str) -> str:
        """
        Normalizza un titolo o ID per l'uso coerente nei nomi dei file.
        Esempio: "Il Silenzio! dei Chip.pdf" -> "il_silenzio_dei_chip"
        """
        if not text:
            return "unknown"
        import re
        import os
        # Rimuove estensione se presente
        name = os.path.splitext(text)[0]
        # Lowercase e sostituisce TUTTO quello che non è alfanumerico con _
        name = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
        # Rimuove underscores duplicati e pulisce estremità
        name = re.sub(r'_+', '_', name).strip('_')
        return name

    def _ensure_directories(self):
        """Assicura che tutte le directory esistano"""
        if self.project_id:
            # Struttura moderna isolata per progetto
            dirs = [
                "source",
                "stages/stage_0/output",
                "stages/stage_a/output", 
                "stages/stage_b/output", 
                "stages/stage_b2/output",
                "stages/stage_c/output",
                "stages/stage_d/output",
                "stages/stage_e/output",
                "stages/stage_f/output",
                "final",
                "logs"
            ]
            root = self.project_root
            for dir_name in dirs:
                path = root / dir_name
                path.mkdir(parents=True, exist_ok=True)
        else:
            # Assicura solo la radice dei progetti
            (self.base_path / "projects").mkdir(parents=True, exist_ok=True)
    
    def save_stage_input(self, stage: str, data: Dict[str, Any], book_id: str, 
                        block_id: Optional[str] = None,
                        include_timestamp: bool = True) -> str:
        """Salva input di uno stage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        components = [book_id]
        if block_id:
            components.append(block_id)
        
        if include_timestamp:
            filename = "-".join(components) + f"-{timestamp}.json"
        else:
            filename = "-".join(components) + ".json"
        
        # Routing: Project-specific vs Legacy
        if self.project_id:
            output_dir = self.project_root / "stages" / f"stage_{stage}" / "output" # Scriviamo in output per praticità
        else:
            output_dir = self.base_path / f"stage_{stage}" / "input"
            
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        
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
                         custom_filename: Optional[str] = None,
                         include_timestamp: bool = True) -> str:
        """Salva output di uno stage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Coherence: Force normalization on book_id (which is our project title)
        book_id = self.normalize_id(book_id)
        
        components = []
        if block_id:
            # Se block_id contiene già book_id- all'inizio, non raddoppiarlo
            if block_id.startswith(f"{book_id}-"):
                components.append(block_id)
            else:
                components.append(f"{book_id}-{block_id}")
        else:
            components.append(book_id)
            
        if scene_id:
            components.append(scene_id)
        if custom_filename:
            components.append(custom_filename)
        
        if include_timestamp:
            filename = "-".join(components) + f"-{timestamp}.json"
        else:
            filename = "-".join(components) + ".json"
        
        # Routing: Project-specific vs Legacy
        if self.project_id:
            output_dir = self.project_root / "stages" / f"stage_{stage}" / "output"
        else:
            output_dir = self.base_path / f"stage_{stage}" / "output"
            
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            self.logger.info(f"✅ Salvato output Stage {stage}: {filepath}")
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
        # Routing: Project-specific vs Legacy
        if self.project_id:
            output_dir = self.project_root / "stages" / f"stage_{stage}" / "output"
        else:
            output_dir = self.base_path / f"stage_{stage}" / "output"
        
        if not output_dir.exists():
            return None

        book_id = self.normalize_id(book_id)
        if block_id:
            # Se block_id contiene già book_id- all'inizio, non raddoppiarlo
            if block_id.startswith(f"{book_id}-"):
                pattern = f"{block_id}*.json"
            else:
                pattern = f"{book_id}-{block_id}*.json"
        else:
            pattern = f"{book_id}-*.json"
        
        files = list(output_dir.glob(pattern))
        
        if not files:
            # self.logger.warning(f"⚠️ Nessun output trovato per {book_id}_{block_id}")
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