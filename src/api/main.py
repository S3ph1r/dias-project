from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from typing import List, Dict, Any
import datetime

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.registry import ActiveTaskTracker
from src.common.logging_setup import get_logger
from src.common.persistence import DiasPersistence

logger = get_logger("api_hub")

app = FastAPI(title="DIAS API Hub", version="1.0.0")

# Base directory for data scanning (execution root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Instanziazione Persistence per normalizzazione e gestione file
persistence = DiasPersistence(base_path=str(BASE_DIR / "data"))

app = FastAPI(title="DIAS API Hub", version="1.0.0")

# Base directory for data scanning (execution root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Enable CORS for SvelteKit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the dashboard URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = get_config()
redis_client = get_redis_client()

@app.get("/")
async def root():
    return {
        "status": "online",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "DIAS API Hub"
    }

@app.get("/aria/nodes")
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

@app.get("/projects")
async def list_projects() -> List[Dict[str, Any]]:
    """
    List all projects based on files in data/stage_a/output/
    """
    projects_dir = BASE_DIR / "data" / "stage_a" / "output"
    if not projects_dir.exists():
        return []
    
    projects = []
    found_titles = {} # Map title -> {last_mod, count}
    
    for file in projects_dir.glob("*.json"):
        parts = file.stem.split("-chunk-")
        if len(parts) > 0:
            title = parts[0]
            mtime = file.stat().st_mtime
            if title not in found_titles:
                found_titles[title] = {"last_modified": mtime, "count": 1}
            else:
                found_titles[title]["count"] += 1
                if mtime > found_titles[title]["last_modified"]:
                    found_titles[title]["last_modified"] = mtime
    
    for title, info in found_titles.items():
        projects.append({
            "id": title,
            "name": title.replace("-", " "),
            "total_chunks": info["count"],
            "last_modified": datetime.datetime.fromtimestamp(info["last_modified"]).isoformat()
        })
    
    return projects

# Stage Mapping for Dashboard
STAGE_MAP = {
    "stage_a": "Text Ingester",
    "stage_b": "Macro Analyzer",
    "stage_c": "Scene Direction",
    "stage_d": "Voice Generation (Qwen3TTS)",
    "stage_e": "Music Generation",
    "stage_f": "Audio Mixing",
    "stage_g": "Mastering Engine"
}

@app.get("/projects/{project_id}")
async def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Detailed progress for a specific book.
    Calculates progress and returns file lists for each stage.
    """
    project_id = persistence.normalize_id(project_id)
    base_path = BASE_DIR / "data"
    stages = ["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f", "stage_g"]
    
    detailed_stages = []
    total_chunks = 0
    
    # 1. Get total chunks from Stage A
    stage_a_dir = base_path / "stage_a" / "output"
    stage_a_files = sorted([f.name for f in stage_a_dir.glob(f"{project_id}-chunk-*.json")])
    total_chunks = len(stage_a_files)
    
    for stage_key in stages:
        stage_dir = base_path / stage_key / "output"
        files = []
        if stage_dir.exists():
            files = sorted([f.name for f in stage_dir.glob(f"{project_id}-*")])
        
        # Calculate status
        status = "pending"
        if len(files) > 0:
            if stage_key == "stage_c":
                status = "done" if any("scenes-" in f for f in files) else "in_progress"
            elif len(files) >= total_chunks and total_chunks > 0:
                status = "done"
            else:
                status = "in_progress"

        detailed_stages.append({
            "id": stage_key,
            "name": STAGE_MAP.get(stage_key, stage_key),
            "status": status,
            "files": files,
            "is_placeholder": stage_key in ["stage_e", "stage_f", "stage_g"]
        })

    completed = sum(1 for s in detailed_stages if s["status"] == "done")
    progress_pct = (completed / len(stages)) * 100

    return {
        "project_id": project_id,
        "name": project_id.replace("-", " "),
        "total_chunks": total_chunks,
        "overall_progress": round(progress_pct, 2),
        "stages": detailed_stages
    }

@app.get("/info/quota")
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

@app.delete("/projects/{project_id}/stages/{stage_id}")
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
            
        # 2. Get project clean title (assuming project_id is already the clean title for now or lookup)
        # For DIAS, project_id is usually the clean_title
        clean_title = persistence.normalize_id(project_id)
        
        output_path = BASE_DIR / "data" / target_dir_name / "output" / clean_title
        
        # 3. Delete files if directory exists
        import shutil
        if output_path.exists():
            shutil.rmtree(output_path)
            
        # 4. Identify previous stage and re-enqueue
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
            source_path = BASE_DIR / "data" / prev_stage / "output" / clean_title
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

@app.get("/projects/{project_id}/resume/check")
async def check_resume_status(project_id: str):
    """
    Scans Stage C outputs to detect which voices are already assigned.
    Returns a summary of voice usage.
    """
    try:
        clean_title = persistence.normalize_id(project_id)
        source_dir = BASE_DIR / "data" / "stage_c" / "output"
        
        if not source_dir.exists():
            return {"status": "no_source", "voices": {}}
            
        voice_counts = {}
        for source_file in source_dir.glob(f"{clean_title}-*.json"):
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

@app.post("/projects/{project_id}/resume")
async def resume_project_pipeline(project_id: str, payload: Dict[str, Any] = None):
    """
    Scans the entire pipeline for the project and enqueues missing tasks.
    """
    try:
        clean_title = persistence.normalize_id(project_id)
        
        # Define the chain of stages - Based on standardized dias.yaml keys
        # Mapping: (source_stage_dir, target_stage_dir, target_input_queue_key)
        stages = [
            ("stage_a", "stage_b", "ingestion"),
            ("stage_b", "stage_c", "semantic"),
            ("stage_c", "stage_d", "voice"), 
        ]
        
        total_pushed = 0
        
        for source_stage, target_stage, queue in stages:
            source_dir = BASE_DIR / "data" / source_stage / "output"
            target_dir = BASE_DIR / "data" / target_stage / "output"
            
            if not source_dir.exists():
                continue
                
            # Scan source for files that don't have a corresponding target
            import re
            for source_file in sorted(source_dir.glob(f"{clean_title}-*.json")):
                with open(source_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract chunk_label from filename if not reliably in data
                match = re.search(r'(chunk-\d+)', source_file.name)
                chunk_from_file = match.group(1) if match else None

                if target_stage == "stage_d":
                    if "scenes" in data:
                        # This is a master file
                        for scene in data["scenes"]:
                            scene_id = scene.get("scene_id")
                            chunk_label = data.get("chunk_label") or chunk_from_file
                            # Usa glob per ignorare il timestamp di Stage D
                            search_pattern = f"{clean_title}-{chunk_label}-{scene_id}-*.json"
                            if not list(target_dir.glob(search_pattern)):
                                # Apply voice override if provided
                                voice_override = payload.get("voice_override") if payload else None
                                if voice_override:
                                    # Create a copy to avoid mutating the original data
                                    scene_to_push = scene.copy()
                                    scene_to_push["voice_id"] = voice_override
                                else:
                                    scene_to_push = scene
                                    
                                # Use dynamic queue name from config for Stage D
                                queue_name = config.queues.dict().get(queue)
                                if queue_name:
                                    redis_client.push_to_queue(queue_name, scene_to_push)
                                    total_pushed += 1
                                else:
                                    logger.error(f"Queue key {queue} not found in config")
                else:
                    # Generic stage logic (e.g. Stage A -> B, Stage B -> C)
                    chunk_label = data.get("chunk_label") or chunk_from_file
                    if chunk_label:
                        search_pattern = f"{clean_title}-{chunk_label}-*.json"
                        if not list(target_dir.glob(search_pattern)):
                            # Use dynamic queue name from config
                            queue_name = config.queues.dict().get(queue)
                            if queue_name:
                                # Schema mapping for Resume
                                message_to_push = data.copy()
                                
                                # Stage B expects 'text', Stage A files have 'block_text'
                                if source_stage == "stage_a" and "block_text" in message_to_push:
                                    message_to_push["text"] = message_to_push["block_text"]
                                
                                # Enforce coherence fields
                                message_to_push["clean_title"] = clean_title
                                message_to_push["chunk_label"] = chunk_label
                                message_to_push["book_id"] = clean_title
                                
                                logger.info(f"Resuming {source_stage} -> {target_stage}: Pushing {chunk_label} (block_id: {message_to_push.get('block_id')}, text_len: {len(message_to_push.get('text', ''))})")
                                
                                redis_client.push_to_queue(queue_name, message_to_push)
                                total_pushed += 1
                            else:
                                logger.error(f"Queue key {queue} not found in config")
                        
        return {"status": "success", "pushed_count": total_pushed}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects/{project_id}/push_scene")
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
    
    # Use BASE_DIR for consistency
    scene_path = BASE_DIR / "data" / "stage_c" / "output" / project_id / scene_file_name
    
    if not scene_path.exists():
        # Fallback search if project_id folder doesn't exist or file is elsewhere
        potential_paths = list(BASE_DIR.glob(f"data/stage_c/output/**/{scene_file_name}"))
        if potential_paths:
            scene_path = potential_paths[0]
        else:
            raise HTTPException(status_code=404, detail=f"Scene file {scene_file_name} not found")
    
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

@app.get("/info/voices")
async def get_available_voices() -> Dict[str, List[str]]:
    """
    Aggregates available voices from all active ARIA nodes.
    """
    try:
        all_voices = set()
        keys = redis_client.keys("aria:global:node:*:status")
        for key in keys:
            data = redis_client.get(key)
            if data:
                node_info = json.loads(data)
                voices = node_info.get("available_voices", [])
                all_voices.update(voices)
        return {"voices": sorted(list(all_voices))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aggregating voices: {str(e)}")

@app.post("/projects/run")
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

@app.post("/projects/{project_id}/control")
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

@app.get("/projects/{project_id}/output")
async def get_project_outputs(project_id: str) -> List[Dict[str, Any]]:
    """
    Lists all generated assets (WAV files) for a specific project.
    """
    project_id = persistence.normalize_id(project_id)
    output_dir = BASE_DIR / "data" / "stage_d" / "output"
    if not output_dir.exists():
        return []
    
    outputs = []
    for file in output_dir.glob(f"{project_id}-*.wav"):
        outputs.append({
            "filename": file.name,
            "size_bytes": file.stat().st_size,
            "url": f"/static/outputs/{file.name}", # Placeholder for the asset server
            "created_at": datetime.datetime.fromtimestamp(file.stat().st_mtime).isoformat()
        })
    return sorted(outputs, key=lambda x: x["filename"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
