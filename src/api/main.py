from fastapi import FastAPI, HTTPException, UploadFile, File, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Sub-path support: set DIAS_APP_BASE=/dias when served behind a reverse proxy
# at a non-root path. Affects audio URL generation.
APP_BASE_PATH = os.environ.get("DIAS_APP_BASE", "").rstrip("/")
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime
import mimetypes

# Assicuriamoci che il server riconosca i file .m4b come audio
mimetypes.add_type('audio/mp4', '.m4b')

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.registry import ActiveTaskTracker
from src.common.logging_setup import get_logger
from src.common.persistence import DiasPersistence
from src.common.audio_utils import get_audio_metrics

logger = get_logger("api_hub")

app = FastAPI(title="DIAS API Hub", version="1.0.0")

api_router = APIRouter()

@api_router.get("/system/workers")
async def get_workers_status():
    """
    Check status of all DIAS workers and Orchestrator.
    """
    workers = {
        "stage_a": "stage_a_text_ingester.py",
        "stage_b": "stage_b_semantic_analyzer.py",
        "stage_c": "stage_c_scene_director.py",
        "stage_d": "stage_d_voice_gen.py",
        "orchestrator": "src.common.orchestrator"
    }
    
    status = {}
    import subprocess
    for key, pattern in workers.items():
        try:
            # Check specifically for python execution of the script or module
            # Using a pattern that is flexible for dots or slashes
            cmd = f"pgrep -f 'python.*{pattern.replace('.', '[./]')}'"
            output = subprocess.check_output(cmd, shell=True).decode()
            if output.strip():
                status[key] = "running"
            else:
                status[key] = "stopped"
        except subprocess.CalledProcessError:
            status[key] = "stopped"
            
    return {"status": "success", "workers": status}

# Base directory for data scanning (execution root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Instanziazione Persistence per normalizzazione e gestione file
persistence = DiasPersistence()
DATA_DIR = persistence.base_path

# Mount static projects directory
# This allows serving audio from /static/projects/{project_id}/stages/stage_d/output/{filename}
projects_dir = DATA_DIR / "projects"
if not projects_dir.exists():
    projects_dir.mkdir(parents=True, exist_ok=True)
if APP_BASE_PATH:
    app.mount(f"{APP_BASE_PATH}/static/projects", StaticFiles(directory=str(projects_dir)), name="projects")
else:
    app.mount("/static/projects", StaticFiles(directory=str(projects_dir)), name="projects")

# ARIA Voice Assets for previews (Sibling directory check)
aria_assets_path = BASE_DIR.parent / "ARIA" / "data" / "assets"
if aria_assets_path.exists():
    app.mount("/aria-assets", StaticFiles(directory=str(aria_assets_path)), name="aria-assets")

aria_legacy_voices_path = BASE_DIR.parent / "ARIA" / "data" / "voices"
if aria_legacy_voices_path.exists():
    app.mount("/aria-assets/legacy_voices", StaticFiles(directory=str(aria_legacy_voices_path)), name="aria-legacy-voices")

# Enable CORS for SvelteKit
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"🌐 INCOMING: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📡 OUTGOING: {request.method} {request.url.path} -> STATUS {response.status_code}")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the dashboard URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = get_config()
redis_client = get_redis_client()

def slugify(text: str) -> str:
    """
    Convert a string into a clean project ID using persistence standards.
    """
    return persistence.normalize_id(text)

from fastapi import UploadFile, File, BackgroundTasks
import shutil

def extract_text_task(file_path: Path, txt_path: Path, project_id: str):
    """
    Background task to extract text from PDF/EPUB and update project status.
    """
    logger = get_logger("api_worker")
    logger.info(f"Starting background text extraction for {project_id}...")
    try:
        import fitz
        doc = fitz.open(str(file_path))
        text_parts = []
        for i, page in enumerate(doc):
            page_text = page.get_text().strip()
            if page_text:
                text_parts.append(page_text)
        
        full_text = "\n\f\n".join(text_parts)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
            
        logger.info(f"Successfully extracted {len(full_text)} chars for {project_id}")
        
        # Update config to ready
        config_path = file_path.parent.parent / "config.json"
        if config_path.exists():
            with open(config_path) as f: cfg = json.load(f)
            cfg["status"] = "upload_complete"
            with open(config_path, "w") as f: json.dump(cfg, f, indent=4)
            
    except Exception as e:
        logger.error(f"Background extraction failed for {project_id}: {str(e)}")
        config_path = file_path.parent.parent / "config.json"
        if config_path.exists():
            with open(config_path) as f: cfg = json.load(f)
            cfg["status"] = "error"
            cfg["error"] = str(e)
            with open(config_path, "w") as f: json.dump(cfg, f, indent=4)

            
        # Trigger Stage 0 (Intelligence) via Redis
        # redis_client.rpush("dias:q:0:intel", json.dumps({"project_id": project_id}))
        
        return {
            "status": "success",
            "project_id": project_id,
            "message": f"Project '{project_id}' created and file saved."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")

@api_router.get("/health")
async def root():
    return {
        "status": "online",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "DIAS API Hub"
    }

@api_router.get("/aria/nodes")
async def get_aria_nodes() -> List[Dict[str, Any]]:
    """
    Get all active ARIA nodes by searching for heartbeat keys in Redis.
    Pattern: aria:global:node:*:status
    """
    try:
        nodes = []
        keys = redis_client.keys("aria:global:node:*:status")
        for key in keys:
            data = redis_client.get(key)
            if data:
                nodes.append(json.loads(data))
        return nodes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching ARIA nodes: {str(e)}")

@api_router.get("/projects")
async def list_projects() -> List[Dict[str, Any]]:
    """
    List all projects from data/projects/
    """
    projects_dir = DATA_DIR / "projects"
    projects = []
    
    if projects_dir.exists():
        for d in projects_dir.iterdir():
            if d.is_dir():
                pid = d.name
                config_path = d / "config.json"
                status = "new"
                chunk_count = 0
                
                if config_path.exists():
                    try:
                        with open(config_path) as f:
                            cfg = json.load(f)
                            status = cfg.get("status", "unknown")
                            
                            # Count chunks by scanning stage_a
                            stage_a_dir = d / "stages" / "stage_a" / "output"
                            if stage_a_dir.exists():
                                chunk_count = len(list(stage_a_dir.glob("*.json")))
                                
                            projects.append({
                                "id": pid,
                                "name": pid.replace("-", " "),
                                "total_chunks": chunk_count,
                                "last_modified": datetime.datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
                                "status": status
                            })
                    except: pass
    
    # Sort by last modified
    return sorted(projects, key=lambda x: x["last_modified"], reverse=True)

@api_router.post("/projects/upload")
async def upload_project(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a new project file (PDF, EPUB, DOCX), create directory,
    and trigger background text extraction.
    """
    # 1. Normalize ID using persistence standard
    project_id = persistence.normalize_id(file.filename)
    project_dir = DATA_DIR / "projects" / project_id
    
    project_dir.mkdir(parents=True, exist_ok=True)
    source_dir = project_dir / "source"
    source_dir.mkdir(exist_ok=True)
    
    # 2. Save original file (nome originale preservato)
    file_path = source_dir / file.filename
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    # 3. Path for text extraction - Usa ID normalizzato per il file di testo
    txt_filename = f"{project_id}.txt"
    txt_path = source_dir / txt_filename
    
    # 4. Initialize config with 'processed_text' pointer
    config_path = project_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump({
            "project_id": project_id,
            "original_filename": file.filename,
            "processed_text": f"source/{txt_filename}", # Puntatore deterministico
            "status": "extracting",
            "created_at": datetime.datetime.now().isoformat()
        }, f, indent=4)

    # 5. Trigger extraction in background to avoid timeouts
    background_tasks.add_task(extract_text_task, file_path, txt_path, project_id)
    
    return {
        "project_id": project_id,
        "status": "extracting",
        "message": f"Project {project_id} uploaded. Text extraction started in background."
    }

def get_project_dir(project_id: str) -> Path:
    """
    Helper to find the project directory case-insensitively and with flexible normalization.
    """
    # 1. Try case-insensitive search in projects folder (most robust)
    projects_root = DATA_DIR / "projects"
    if projects_root.exists():
        for d in projects_root.iterdir():
            if d.is_dir():
                # Check normalized match
                if persistence.normalize_id(d.name) == persistence.normalize_id(project_id):
                    return d
                # Check direct match
                if d.name.lower() == project_id.lower():
                    return d
                    
    # 2. Fallback to direct path
    return DATA_DIR / "projects" / persistence.normalize_id(project_id)

@api_router.post("/projects/{project_id}/analyze")
async def analyze_project(project_id: str):
    """
    Manually trigger Stage 0 Intelligence analysis for a project.
    Lancia automaticamente il worker in modalità on-demand per il progetto specificato.
    """
    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
    actual_project_id = project_dir.name
    
    # 1. Pulisce la coda Redis da eventuali vecchi messaggi per questo progetto
    # (Evita duplicati se un worker classico dovesse svegliarsi)
    try:
        queue_name = "dias:q:0:intel"
        # Estraiamo tutti i messaggi, filtriamo e rimettiamo quelli che non ci riguardano
        # È un'operazione atomica simulata per pulizia
        all_msgs = redis_client.client.lrange(queue_name, 0, -1)
        for msg_raw in all_msgs:
            msg_data = json.loads(msg_raw)
            if msg_data.get("project_id") == actual_project_id:
                redis_client.client.lrem(queue_name, 0, msg_raw)
        logger.info(f"🧹 Pulizia coda Redis completata per {actual_project_id}")
    except Exception as e:
        logger.warning(f"⚠️ Impossibile pulire la coda Redis: {e}")

    # 2. GUARD: Controllo se è già in esecuzione
    import subprocess
    try:
        # Cerchiamo il processo specifico per questo progetto
        pgrep_cmd = ["pgrep", "-f", f"stage_0_intel.py.*--project-id {actual_project_id}"]
        pgrep_check = subprocess.run(pgrep_cmd, capture_output=True)
        if pgrep_check.returncode == 0:
             return {"status": "running", "message": f"L'analisi per {actual_project_id} è già in corso."}
    except Exception as e:
        logger.error(f"Errore controllo processi pgrep: {e}")

    # 2. Individuo il file .txt sorgente (necessario per replicare il comportamento legacy)
    source_dir = project_dir / "source"
    txt_files = list(source_dir.glob("*.txt"))
    if not txt_files:
        raise HTTPException(status_code=400, detail="Source text file (.txt) not found in project sources.")
    txt_filename = txt_files[0].name

    # 3. AUTO-TRIGGER: Avvia il worker in background in modalità on-demand
    try:
        python_bin = BASE_DIR / ".venv" / "bin" / "python3"
        stage_0_script = BASE_DIR / "src" / "stages" / "stage_0_intel.py"
        log_file = BASE_DIR / "logs" / "stage_0_intel.log"
        
        # Comando detached per non bloccare l'API, passando --project-id e --source-file
        # Usiamo le virgolette per gestire caratteri speciali e spazi nel nome file
        cmd = f'nohup env PYTHONPATH=. {python_bin} {stage_0_script} --project-id "{actual_project_id}" --source-file "{txt_filename}" >> {log_file} 2>&1 &'
        subprocess.Popen(cmd, shell=True, cwd=BASE_DIR)
        
        # Aggiorno anche il config.json per riflettere lo stato subito in Dashboard
        config_path = project_dir / "config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            cfg["status"] = "analisi_in_corso"
            with open(config_path, 'w') as f:
                json.dump(cfg, f, indent=4)
        
        logger.info(f"🚀 Innescato Auto-Stage 0 On-Demand per {actual_project_id}")
        return {"status": "started", "message": f"Analisi avviata per {actual_project_id}"}
    except Exception as e:
        logger.error(f"Errore auto-trigger Stage 0: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Update status in config
    config_path = project_dir / "config.json"
    if config_path.exists():
        with open(config_path) as f: cfg = json.load(f)
        cfg["status"] = "analyzing"
        with open(config_path, "w") as f: json.dump(cfg, f, indent=4)

    return {
        "project_id": actual_project_id,
        "status": "analyzing",
        "message": "Intelligence Analysis triggered automatically."
    }

@api_router.get("/projects/{project_id}/fingerprint")
async def get_project_fingerprint(project_id: str):
    """
    Return the book intelligence fingerprint (output of Stage 0).
    """
    project_dir = get_project_dir(project_id)
    # Nuova logica: Usa persistence per risolvere il path coerente
    current_persistence = DiasPersistence(project_id=project_dir.name)
    fingerprint_path = current_persistence.get_fingerprint_path()
    
    if not fingerprint_path.exists():
        raise HTTPException(status_code=404, detail="Intelligence analysis not yet completed or not found.")
        
    with open(fingerprint_path) as f:
        data = json.load(f)
        
    # Alias di compatibilità per Dashboard Legacy
    if "chapters_list" in data and "chapters" not in data:
        data["chapters"] = data["chapters_list"]
    
    # Assicuro presenza metadata base per evitare crash frontend
    if "metadata" not in data:
        data["metadata"] = {"title": project_id, "author": "Unknown"}
        
    return data

@api_router.get("/projects/{project_id}/preproduction")
async def get_project_preproduction(project_id: str):
    """
    Return the pre-production configuration (casting assignments, etc.).
    """
    project_dir = get_project_dir(project_id)
    current_persistence = DiasPersistence(project_id=project_dir.name)
    path = current_persistence.get_preproduction_path()
    
    if not path.exists():
        # Return default structure
        return {"casting": {}, "palette_choice": None}
        
    with open(path) as f:
        return json.load(f)

@api_router.post("/projects/{project_id}/preproduction")
async def save_project_preproduction(project_id: str, data: Dict[str, Any]):
    """
    Save the pre-production configuration by merging with existing data.
    """
    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
        
    current_persistence = DiasPersistence(project_id=project_dir.name)
    path = current_persistence.get_preproduction_path()
    
    # Carico i dati esistenti per fare il MERGE invece del BLANK OVERWRITE
    existing_data = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception as e:
            logger.error(f"Errore caricamento pre-produzione esistente per merge: {e}")

    # Applico le modifiche (Merge selettivo)
    if "casting" in data:
        if "casting" not in existing_data:
            existing_data["casting"] = {}
        # Unisco le scelte (Nome -> Voce) mantenendo eventuali altri campi nel dossier
        existing_data["casting"].update(data["casting"])
        
    if "palette_choice" in data:
        existing_data["palette_choice"] = data["palette_choice"]
        
    if "global_voice" in data:
        existing_data["global_voice"] = data["global_voice"]

    # Altri metadati (come theatrical_standard) vengono preservati perché non sovrascritti nel dict
    
    logger.info(f"💾 Salvataggio (Smart Merge) Pre-produzione per {project_id}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=4)
        
    return {"status": "success", "message": "Pre-production configuration merged and saved."}

# Stage Mapping for Dashboard
STAGE_MAP = {
    "stage_a": "Text Ingester",
    "stage_b": "Macro Analyzer",
    "stage_c": "Scene Direction",
    "stage_d": "Voice Generation (Qwen3TTS)",
    "stage_e": "Music Generation",
    "stage_f": "Audiobook Mastering",
    "stage_g": "Mastering Engine"
}

@api_router.get("/projects/{project_id}")
async def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Detailed progress for a specific book.
    Calculates progress and returns file lists for each stage.
    """
    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
        
    actual_project_id = project_dir.name
    stages_root = project_dir / "stages"
    
    stages = ["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f", "stage_g"]
    
    detailed_stages = []
    total_chunks = 0
    
    # 1. Get total chunks from Stage A
    stage_a_dir = stages_root / "stage_a" / "output"
    # Note: in project-centric, names might be normalized or keep project prefix
    stage_a_files = sorted([f.name for f in stage_a_dir.glob("*.json") if "chunk-" in f.name])
    total_chunks = len(stage_a_files)
    
    for stage_key in stages:
        stage_dir = stages_root / stage_key / "output"
        files = []
        if stage_dir.exists():
            # In project-centric, we list all files in the output dir of that stage
            files = sorted([f.name for f in stage_dir.glob("*.json")])
            # If it's stage_d or f, we might have .wav too
            if stage_key in ["stage_d", "stage_f", "stage_g"]:
                files.extend(sorted([f.name for f in stage_dir.glob("*.wav")]))
                files = sorted(files)
        
        # Calculate status
        status = "pending"
        if len(files) > 0:
            if stage_key == "stage_c":
                status = "done" if any("scenes" in f for f in files) else "in_progress"
            elif len(files) >= total_chunks and total_chunks > 0:
                status = "done"
            else:
                status = "in_progress"

        detailed_stages.append({
            "id": stage_key,
            "name": STAGE_MAP.get(stage_key, stage_key),
            "status": status,
            "files": files,
            "is_placeholder": stage_key in ["stage_e", "stage_g"]
        })

    completed = sum(1 for s in detailed_stages if s["status"] == "done")
    progress_pct = (completed / len(stages)) * 100

    active_stage_key = f"dias:project:{actual_project_id}:active_stage"
    active_stage = redis_client.get(active_stage_key)
    if active_stage:
        active_stage = active_stage.decode('utf-8') if isinstance(active_stage, bytes) else active_stage
    else:
        active_stage = None

    # 2. Get status from config.json
    project_status = "idle"
    config_path = project_dir / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = json.load(f)
                project_status = cfg.get("status", "idle")
        except:
            pass

    if project_status == "completed":
        progress_pct = 100.0

    # Audiobook Master Check
    final_dir = project_dir / "final"
    audiobook_info = None
    if final_dir.exists():
        m4b_files = sorted(list(final_dir.glob("*.m4b")))
        if m4b_files:
            audiobook_info = {
                "url": f"{APP_BASE_PATH}/static/projects/{actual_project_id}/final/{m4b_files[0].name}",
                "filename": m4b_files[0].name,
                "size": m4b_files[0].stat().st_size,
                "chapters_file": f"{APP_BASE_PATH}/static/projects/{actual_project_id}/final/metadata.txt"
            }

    return {
        "project_id": actual_project_id,
        "name": actual_project_id.replace("-", " "),
        "status": project_status,
        "total_chunks": total_chunks,
        "overall_progress": round(progress_pct, 2),
        "active_stage": active_stage,
        "stages": detailed_stages,
        "audiobook": audiobook_info
    }

@api_router.get("/projects/{project_id}/status/live")
async def get_project_live_status(project_id: str) -> Dict[str, Any]:
    """
    Lightweight polling endpoint — returns only counters, no file lists.
    Use this for frontend auto-refresh instead of the full /projects/{id} endpoint.
    Typical response size: ~200 bytes vs ~270KB for the full endpoint.
    """
    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    actual_project_id = project_dir.name

    # Project status from config.json
    project_status = "idle"
    config_path = project_dir / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                project_status = json.load(f).get("status", "idle")
        except Exception:
            pass

    # Active stage from Redis
    active_stage_raw = redis_client.get(f"dias:project:{actual_project_id}:active_stage")
    active_stage = (active_stage_raw.decode('utf-8') if isinstance(active_stage_raw, bytes) else active_stage_raw) if active_stage_raw else None

    # Orchestrator running check
    import subprocess
    try:
        out = subprocess.check_output("pgrep -f 'python.*src.common.orchestrator'", shell=True).decode()
        orchestrator_running = bool(out.strip())
    except subprocess.CalledProcessError:
        orchestrator_running = False

    # Global pause state
    paused_raw = redis_client.get("dias:status:paused")
    paused_reason = (paused_raw.decode('utf-8') if isinstance(paused_raw, bytes) else paused_raw) if paused_raw else None

    # Stage D voice progress: WAV done vs scene JSON total (scene-*.json only)
    stage_d_dir = project_dir / "stages" / "stage_d" / "output"
    stage_c_dir = project_dir / "stages" / "stage_c" / "output"
    voice_done = len(list(stage_d_dir.glob("*.wav"))) if stage_d_dir.exists() else 0
    voice_total = len([f for f in stage_c_dir.glob("*scene-*.json") if "scenes" not in f.name]) if stage_c_dir.exists() else 0

    return {
        "project_id": actual_project_id,
        "status": project_status,
        "active_stage": active_stage,
        "orchestrator_running": orchestrator_running,
        "paused_reason": paused_reason,
        "voice_done": voice_done,
        "voice_total": voice_total,
    }


@api_router.get("/info/quota")
async def get_quota_info() -> Dict[str, Any]:
    """Returns the current ARIA/Gemini API quota usage from Redis."""
    try:
        today = datetime.date.today().isoformat()
        daily_key = f"aria:rate_limit:google:daily_count:{today}"
        usage = redis_client.get(daily_key)
        usage = int(usage) if usage else 0
        
        # We assume the limit is 20 (standardized in ARIA)
        limit = 20
        
        return {
            "usage": usage,
            "limit": limit,
            "available": max(0, limit - usage),
            "service": "ARIA centralized"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/projects/{project_id}/stages/{stage_id}")
async def reset_project_stage(project_id: str, stage_id: str):
    """
    Resets a specific stage for a project.
    1. Deletes output files for that stage.
    2. Re-enqueues input files for that stage (from previous stage outputs).
    """
    try:
        # 1. Identify paths
        # Map stage_id to directory name
        stage_map = {
            "stage_a": "stage_a",
            "stage_b": "stage_b",
            "stage_c": "stage_c",
            "stage_d": "stage_d",
            "stage_e": "stage_e",
            "stage_f": "stage_f",
            "stage_g": "stage_g"
        }
        
        target_dir_name = stage_map.get(stage_id)
        if not target_dir_name:
            raise HTTPException(status_code=400, detail=f"Invalid stage_id: {stage_id}")
            
        # 2. Get project clean title
        clean_title = persistence.normalize_id(project_id)
        
        # 3. New project-centric path
        project_persistence = DiasPersistence(project_id=clean_title)
        output_path = project_persistence.project_root / "stages" / target_dir_name / "output"
        
        # 4. Delete files if directory exists
        import shutil
        if output_path.exists():
            for f in output_path.glob("*"):
                if f.is_file(): f.unlink()
                elif f.is_dir(): shutil.rmtree(f)
            logger.info(f"Deleted output files for stage {stage_id} of project {clean_title}")
            
        # 5. --- REDIS DEEP CLEANUP ---
        # Clear Task Registry for this project (Idempotency & Atomic Locks)
        registry_key = f"dias:registry:{clean_title}"
        if redis_client.client.exists(registry_key):
            redis_client.client.delete(registry_key)
            logger.info(f"Deleted registry hash for project {clean_title}")
            
        # Clear Task Tracker (legacy/in-flight)
        tracker_pattern = f"dias:tracker:{clean_title}:*"
        tracker_keys = redis_client.client.keys(tracker_pattern)
        if tracker_keys:
            redis_client.client.delete(*tracker_keys)
            logger.info(f"Cleared {len(tracker_keys)} legacy tracker keys")
            
        # Clear Stage Checkpoint (Orchestrator Position)
        # Mapping stage_id to internal stage name for checkpoint keys
        checkpoint_map = {
            "stage_b": "stage_b",
            "stage_c": "stage_c",
            "stage_d": "stage_d",
            "stage_e": "stage_e",
            "stage_f": "stage_f",
        }
        internal_stage = checkpoint_map.get(stage_id)
        if internal_stage:
            redis_client.client.delete(f"dias:project:{clean_title}:checkpoint:{internal_stage}")
            logger.info(f"Cleared checkpoint for {internal_stage} (project {clean_title})")
            
        # 6. Identify previous stage and re-enqueue
        # This is a bit complex as it depends on the flow. 
        # Simplified: if resetting Stage C, look at Stage B outputs.
        
        # Map of stage to its input queue (keys MUST match dias.yaml:queues)
        queue_map = {
            "stage_b": "ingestion",  # Stage A -> B
            "stage_c": "semantic",   # Stage B -> C
            "stage_d": "voice",      # Stage C -> D
            "stage_e": "music_gen",  # Placeholder
        }
        
        # Map of stage to its source directory (previous stage output)
        source_map = {
            "stage_b": "stage_a",
            "stage_c": "stage_b",
            "stage_d": "stage_c",
            "stage_e": "stage_d",
            "stage_f": "stage_e",
            "stage_g": "stage_f"
        }
        
        prev_stage = source_map.get(stage_id)
        if prev_stage:
            source_path = DATA_DIR / prev_stage / "output" / clean_title
            if source_path.exists():
                count = 0
                for file in source_path.glob("*.json"):
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    config_key = queue_map.get(stage_id)
                    queue_name = config.queues.dict().get(config_key) if config_key else None
                    
                    if queue_name:
                        redis_client.push_to_queue(queue_name, data)
                        count += 1
                    else:
                        logger.error(f"Queue for stage {stage_id} not mapped or found in config")
                return {"status": "success", "message": f"Reset {stage_id} for {clean_title}. Re-enqueued {count} items."}
        
        return {"status": "success", "message": f"Reset {stage_id} for {clean_title}. Output cleared."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/projects/{project_id}/resume/check")
async def check_resume_status(project_id: str):
    """
    Scans Stage C outputs to detect which voices are already assigned.
    Returns a summary of voice usage.
    """
    try:
        clean_id = persistence.normalize_id(project_id)
        source_dir = DATA_DIR / "projects" / clean_id / "stages" / "stage_c" / "output"
        
        if not source_dir.exists():
            return {"status": "no_source", "voices": {}}
            
        voice_counts = {}
        for source_file in source_dir.glob(f"{clean_id}-*.json"):
            # Skip the master file if it exists, only scan individual scenes
            if source_file.name.endswith("-scenes.json"):
                continue
                
            try:
                with open(source_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                voice_id = data.get("voice_id") or "none"
                voice_counts[voice_id] = voice_counts.get(voice_id, 0) + 1
            except:
                continue
                
        return {"status": "success", "voices": voice_counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/projects/{project_id}/resume")
async def resume_project_pipeline(project_id: str, payload: Dict[str, Any] = None):
    """
    Scans the entire pipeline for the project and enqueues missing tasks.
    """
    try:
        clean_title = persistence.normalize_id(project_id)
        
        # --- PERSISTENT SETTINGS (Benchmark Integration) ---
        voice_override = payload.get("voice_override") if payload else None
        if voice_override:
            logger.info(f"Saving persistent voice override '{voice_override}' for project {clean_title}")
            redis_client.client.hset(f"dias:project:{clean_title}:config", "voice_id", voice_override)

        # --- CLEAR GLOBAL PAUSE (se presente) ---
        paused_raw = redis_client.get("dias:status:paused")
        if paused_raw:
            redis_client.client.delete("dias:status:paused")
            logger.info(f"Global pause cleared for project {clean_title}")

        # --- ORCHESTRATOR AUTO-START (solo se non già in esecuzione) ---
        import subprocess
        try:
            search_pattern = f"src[./]common[./]orchestrator.*{clean_title}"
            pgrep_check = subprocess.run(["pgrep", "-f", search_pattern], capture_output=True)
            if pgrep_check.returncode != 0:
                logger.info(f"🚀 Avvio Orchestratore in background per {clean_title}...")
                python_bin = BASE_DIR / ".venv" / "bin" / "python3"
                log_file = BASE_DIR / "logs" / "orchestrator.log"
                cmd = f"nohup {python_bin} -m src.common.orchestrator {clean_title} >> {log_file} 2>&1 &"
                subprocess.Popen(cmd, shell=True, cwd=BASE_DIR)
            else:
                logger.info(f"✅ Orchestratore già attivo per {clean_title}, pausa rimossa.")
        except Exception as e:
            logger.error(f"Errore durante l'avvio dell'orchestratore: {e}")

        return {"status": "success", "message": f"Pipeline resumed for {clean_title}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/projects/{project_id}/unpause")
async def unpause_pipeline(project_id: str):
    """
    Clears the global pipeline pause (dias:status:paused).
    The orchestrator will resume its loop automatically within a few seconds.
    """
    paused_raw = redis_client.get("dias:status:paused")
    if not paused_raw:
        return {"status": "ok", "message": "Pipeline non era in pausa."}
    reason = paused_raw.decode('utf-8') if isinstance(paused_raw, bytes) else paused_raw
    redis_client.client.delete("dias:status:paused")
    logger.info(f"Global pause cleared for project {project_id}. Was: {reason}")
    return {"status": "ok", "message": "Pausa rimossa. L'orchestratore riprenderà entro pochi secondi."}


@api_router.get("/projects/{project_id}/audiobook/chapters")
async def get_audiobook_chapters(project_id: str):
    """Legge i chapter markers dal metadata.txt FFmpeg e restituisce titoli + timestamp."""
    actual_id = persistence.normalize_id(project_id)
    metadata_path = DATA_DIR / "projects" / actual_id / "final" / "metadata.txt"
    if not metadata_path.exists():
        return []

    chapters = []
    current: Dict[str, Any] = {}
    timebase_num, timebase_den = 1, 1000  # default ms

    with open(metadata_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line == "[CHAPTER]":
                if current:
                    chapters.append(current)
                current = {}
            elif line.startswith("TIMEBASE="):
                parts = line.split("=", 1)[1].split("/")
                timebase_num, timebase_den = int(parts[0]), int(parts[1])
            elif line.startswith("START=") and current is not None:
                raw = int(line.split("=", 1)[1])
                current["start_ms"] = int(raw * timebase_num * 1000 / timebase_den)
            elif line.startswith("END=") and current is not None:
                raw = int(line.split("=", 1)[1])
                current["end_ms"] = int(raw * timebase_num * 1000 / timebase_den)
            elif line.startswith("title=") and current is not None:
                current["title"] = line.split("=", 1)[1]

    if current:
        chapters.append(current)
    return chapters


@api_router.post("/projects/{project_id}/master")
async def trigger_audiobook_master(project_id: str):
    """
    Avvia Stage F (Audiobook Mastering) direttamente per il progetto.
    Esegue build_audiobook in background senza passare dall'orchestratore.
    """
    try:
        clean_id = persistence.normalize_id(project_id)
        project_dir = get_project_dir(clean_id)
        if not project_dir.exists():
            raise HTTPException(status_code=404, detail="Project not found")

        import subprocess
        python_bin = BASE_DIR / ".venv" / "bin" / "python3"
        stage_f_script = BASE_DIR / "src" / "stages" / "stage_f_audiobook.py"
        log_file = BASE_DIR / "logs" / "stage_f_audiobook.log"
        cmd = f"nohup env PYTHONPATH=. {python_bin} {stage_f_script} {clean_id} >> {log_file} 2>&1 &"
        subprocess.Popen(cmd, shell=True, cwd=BASE_DIR)

        return {"status": "started", "message": f"Stage F avviato per {clean_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/projects/{project_id}/push_scene")
async def push_scene_to_stage_d(project_id: str, payload: Dict[str, str]):
    """
    Manually pushes a specific Stage C scene JSON to the Stage D queue.
    Supports optional voice_override in the payload.
    """
    scene_file_name = payload.get("scene_file")
    voice_override = payload.get("voice_override")
    
    if not scene_file_name:
        raise HTTPException(status_code=400, detail="Missing scene_file")
    
    project_id = persistence.normalize_id(project_id)
    
    # Nuova logica Sprint 4: Path isolato per progetto
    scene_path = DATA_DIR / "projects" / project_id / "stages" / "stage_c" / "output" / scene_file_name
    
    if not scene_path.exists():
        # Cerca senza prefisso project_id nel nome file se necessario (per compatibilità nomi puliti)
        if not scene_file_name.startswith(project_id):
             alt_name = f"{project_id}-{scene_file_name}"
             alt_path = scene_path.parent / alt_name
             if alt_path.exists():
                 scene_path = alt_path
    
    if not scene_path.exists():
        raise HTTPException(status_code=404, detail=f"Scene file {scene_file_name} not found in project {project_id}")
    
    try:
        with open(scene_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        # Apply voice override if provided
        if voice_override:
            scene_data["voice_id"] = voice_override
        
        target_queue = config.queues.voice
        redis_client.push_to_queue(target_queue, scene_data)
        
        return {
            "status": "success", 
            "message": f"Scene {scene_file_name} pushed to {target_queue}" + (f" with voice {voice_override}" if voice_override else "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error pushing scene: {str(e)}")

@api_router.get("/aria/registry")
async def get_aria_registry() -> Dict[str, Any]:
    """
    Returns the full ARIA Master Registry from Redis.
    This is the 'Digital Storefront' for all available backends and assets.
    """
    try:
        data = redis_client.get("aria:registry:master")
        if data:
            return json.loads(data)
        return {
            "status": "not_found", 
            "message": "Master Registry non ancora pubblicato da ARIA Node."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/info/voices")
async def get_available_voices() -> Dict[str, Any]:
    """
    Aggregates available voices. 
    Prioritizes metadata-rich voices from the Master Registry.
    """
    try:
        all_voices = {}
        
        # 1. Prova il Master Registry (Nuovo Standard Discovery v1.0)
        registry_data = redis_client.get("aria:registry:master")
        if registry_data:
            registry = json.loads(registry_data)
            # assets -> voices
            voices_registry = registry.get("assets", {}).get("voices", {})
            for vid, profile in voices_registry.items():
                all_voices[vid] = profile

        # 2. Fallback / Aggregazione legacy da nodi attivi
        keys = redis_client.keys("aria:global:node:*:status")
        for key in keys:
            data = redis_client.get(key)
            if data:
                node_info = json.loads(data)
                legacy_voices = node_info.get("available_voices", [])
                for vname in legacy_voices:
                    if vname not in all_voices:
                        all_voices[vname] = {
                            "id": vname,
                            "name": vname.capitalize(),
                            "status": "legacy",
                            "metadata": {"description": "Legacy voice (no metadata)"}
                        }
        
        return {"voices": all_voices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aggregating voices: {str(e)}")

@api_router.post("/projects/run")
async def run_project(payload: Dict[str, Any]):
    """
    Triggers the execution of a new project or resumes an existing one.
    Expected payload: { "project_id": "...", "input_path": "...", "config": {...} }
    """
    project_id = payload.get("project_id")
    input_path = payload.get("input_path")
    
    if not project_id:
        raise HTTPException(status_code=400, detail="Missing project_id")

    # In a real implementation, this would trigger Stage A script or push to a control queue
    # For now, we simulate the 'Suspend/Resume' logic via Redis semaphores
    try:
        redis_client.set(f"dias:control:{project_id}:status", "running")
        # Logica per avviare il processo fisico se necessario (subprocess)
        return {"status": "success", "message": f"Project {project_id} started/resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting project: {str(e)}")

@api_router.post("/projects/{project_id}/control")
async def control_project(project_id: str, payload: Dict[str, str]):
    """
    Controls the flow of a project using Redis semaphores.
    Allowed actions: "start", "suspend", "resume", "stop"
    """
    project_id = persistence.normalize_id(project_id)
    action = payload.get("action")
    if action not in ["start", "suspend", "resume", "stop"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    try:
        if action == "stop":
            redis_client.set(f"dias:control:{project_id}:status", "stopped")
            redis_client.set(f"dias:control:{project_id}:semaphore", "red")
        elif action == "suspend":
            redis_client.set(f"dias:control:{project_id}:semaphore", "red")
        elif action == "resume" or action == "start":
            redis_client.set(f"dias:control:{project_id}:status", "running")
            redis_client.set(f"dias:control:{project_id}:semaphore", "green")
            
        return {"status": "success", "action_applied": action}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying control: {str(e)}")

@api_router.get("/projects/{project_id}/chapters")
async def get_project_chapters(project_id: str):
    """
    Get all chapters for a project by scanning stage_c output in the project folder.
    """
    stage_c_dir = DATA_DIR / "projects" / project_id / "stages" / "stage_c" / "output"
    if not stage_c_dir.exists():
        return []
    
    chapters = {}
    # Find all master files: {project_id}-chunk-{###}-micro-{###}-scenes.json
    for file in stage_c_dir.glob("*-micro-*-scenes.json"):
        match = re.search(r"chunk-(\d{3})", file.name)
        if not match: continue
        
        chunk_id = match.group(1)
        if chunk_id not in chapters:
            chapters[chunk_id] = {
                "id": chunk_id,
                "title": f"Chapter {chunk_id}",
                "status": "completed",
                "scene_count": 0
            }
        
        try:
            with open(file) as f:
                data = json.load(f)
                chapters[chunk_id]["scene_count"] += len(data.get("scenes", []))
                
                # Count WAVs for this specific chunk/micro
                stage_d_dir = stage_c_dir.parent.parent / "stage_d" / "output"
                if stage_d_dir.exists():
                    match_micro = re.search(r"micro-(\d{3})", file.name)
                    if match_micro:
                        micro_id = match_micro.group(1)
                        # Count WAVs matching this chunk and micro
                        wav_pattern = f"*-chunk-{chunk_id}-micro-{micro_id}-*.wav"
                        wav_count = len(list(stage_d_dir.glob(wav_pattern)))
                        if "wav_count" not in chapters[chunk_id]:
                             chapters[chunk_id]["wav_count"] = 0
                        chapters[chunk_id]["wav_count"] += wav_count

                if chapters[chunk_id]["title"].startswith("Chapter"):
                    t = data.get("chapter_title")
                    if t: chapters[chunk_id]["title"] = t
        except: pass
        
    return sorted(list(chapters.values()), key=lambda x: x["id"])

@api_router.get("/projects/{project_id}/chapters/{chapter_id}/scenes")
async def get_chapter_scenes(project_id: str, chapter_id: str):
    """
    Get all scenes for a specific chapter from the project folder.
    """
    stage_c_dir = DATA_DIR / "projects" / project_id / "stages" / "stage_c" / "output"
    stage_d_dir = DATA_DIR / "projects" / project_id / "stages" / "stage_d" / "output"
    
    scenes = []
    # Pattern: {project_id}-chunk-{chapter_id}-micro-*-scenes.json
    pattern = f"*-chunk-{chapter_id}-micro-*-scenes.json"
    
    for file in sorted(stage_c_dir.glob(pattern)):
        try:
            with open(file) as f:
                data = json.load(f)
                for scene in data.get("scenes", []):
                    scene_idx = scene.get("scene_id", "001")
                    # liberal match for both old and new formats
                    # if scene_idx is full (e.g. chunk-001-micro-000-scene-001), use it directly
                    if "-scene-" in scene_idx:
                         search_pattern = f"*{scene_idx}.wav"
                    else:
                         search_pattern = f"*scene-{scene_idx}.wav"
                         
                    wav_matches = list(stage_d_dir.glob(search_pattern))
                    
                    if wav_matches:
                        wav_path = wav_matches[0]
                        rel_url = wav_path.relative_to(persistence.base_path / "projects")
                        scene["audio_url"] = f"{APP_BASE_PATH}/static/projects/{rel_url}"
                        
                        # Also check for JSON metadata in Stage D
                        prod_file = wav_path.with_suffix(".json")
                        if prod_file.exists():
                            with open(prod_file) as pf:
                                prod_data = json.load(pf)
                                scene["voice_id"] = prod_data.get("voice_id", scene.get("voice_id"))
                                scene["instruct"] = prod_data.get("instruct", scene.get("instruct"))
                                scene["text"] = prod_data.get("text", scene.get("text"))
                    
                    scenes.append(scene)
        except: pass
        
    return scenes

@api_router.get("/projects/{project_id}/scenes/{scene_id}/metrics")
async def get_scene_metrics(project_id: str, scene_id: str, chapter_id: Optional[str] = None):
    """
    Calculate audio metrics for a scene.
    """
    stage_d_dir = DATA_DIR / "projects" / project_id / "stages" / "stage_d" / "output"
    
    if "-scene-" in scene_id:
        target_scene_idx = scene_id.split("-scene-")[-1]
    else:
        target_scene_idx = scene_id

    if chapter_id:
        pattern = f"cap-{chapter_id}-scene-{target_scene_idx}.wav"
    else:
        pattern = f"cap-*-scene-{target_scene_idx}.wav"
        
    wav_files = list(stage_d_dir.glob(pattern))
    if not wav_files:
        raise HTTPException(status_code=404, detail="Audio file not found")
        
    wav_path = wav_files[0]
    try:
        metrics = get_audio_metrics(str(wav_path))
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/projects/{project_id}/scenes/{scene_id}/retry")
async def retry_scene(project_id: str, scene_id: str, payload: Dict[str, Any] = None):
    """
    Re-queue a scene for Stage D (Voice Gen).
    """
    stage_c_dir = DATA_DIR / "projects" / project_id / "stages" / "stage_c" / "output"
    
    if "-scene-" in scene_id:
        scene_file = stage_c_dir / f"{scene_id}.json"
    else:
        results = list(stage_c_dir.glob(f"*-scene-{scene_id}.json"))
        scene_file = results[0] if results else None
        
    if not scene_file or not scene_file.exists():
        raise HTTPException(status_code=404, detail="Original scene metadata not found")

    try:
        with open(scene_file) as f:
            message = json.load(f)
            
        if payload:
            if "instruct" in payload:
                backend = message.get("tts_backend", "")
                if "qwen3" in backend.lower(): message["qwen3_instruct"] = payload["instruct"]
                elif "eleven" in backend.lower(): message["eleven_instruct"] = payload["instruct"]
                else: message["instruct"] = payload["instruct"]
            
            if "voice_id" in payload:
                message["voice_id"] = payload["voice_id"]
        
        redis_client.rpush("dias:q:4:regia", json.dumps(message))
        return {"status": "success", "message": f"Scene {scene_id} re-queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if APP_BASE_PATH:
    app.include_router(api_router, prefix=f"{APP_BASE_PATH}/api")
else:
    app.include_router(api_router, prefix="/api")

# ─── Svelte static build (deve essere registrato DOPO tutte le API routes) ───
# Build generata con: PUBLIC_BASE_PATH=/dias npm run build
# Servita da FastAPI su porta 8000; nginx (CT202) espone a /dias/ SENZA strip del prefisso.
# CT201 riceve sempre path completi (/dias/...) sia da nginx che da accesso diretto.

_svelte_build = BASE_DIR / "src" / "dashboard" / "build"
if _svelte_build.exists():
    # Asset Vite: montaggio SOLO al path prefissato (CT201 riceve sempre /dias/_app/...)
    if (_svelte_build / "_app").exists():
        if APP_BASE_PATH:
            app.mount(f"{APP_BASE_PATH}/_app", StaticFiles(directory=str(_svelte_build / "_app")), name="svelte-app")
        else:
            app.mount("/_app", StaticFiles(directory=str(_svelte_build / "_app")), name="svelte-app")

    @app.get("/", include_in_schema=False)
    async def _serve_index():
        # Redirect a base path se configurato (evita loop SvelteKit su accesso diretto)
        if APP_BASE_PATH:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(f"{APP_BASE_PATH}/", status_code=302)
        return FileResponse(_svelte_build / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def _serve_spa(path: str):
        """SPA catch-all: serve file se esiste, altrimenti index.html per il routing Svelte."""
        candidate = _svelte_build / path
        if candidate.is_file():
            return FileResponse(candidate)
        # Strip base path prefix (es. "dias/robots.txt" → "robots.txt")
        if APP_BASE_PATH:
            base_strip = APP_BASE_PATH.lstrip("/") + "/"
            if path.startswith(base_strip):
                candidate2 = _svelte_build / path[len(base_strip):]
                if candidate2.is_file():
                    return FileResponse(candidate2)
        return FileResponse(_svelte_build / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
