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

@app.post("/projects/{project_id}/push_scene")
async def push_scene_to_stage_d(project_id: str, payload: Dict[str, str]):
    """
    Manually pushes a specific Stage C scene JSON to the Stage D queue.
    """
    scene_file_name = payload.get("scene_file")
    if not scene_file_name:
        raise HTTPException(status_code=400, detail="Missing scene_file")
    
    scene_path = BASE_DIR / "data" / "stage_c" / "output" / scene_file_name
    if not scene_path.exists():
        # Search in subfolders
        potential_paths = list(BASE_DIR.glob(f"data/stage_c/output/**/{scene_file_name}"))
        if potential_paths:
            scene_path = potential_paths[0]
        else:
            raise HTTPException(status_code=404, detail=f"Scene file {scene_file_name} not found")

    try:
        with open(scene_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        target_queue = "dias:queue:4:voice_gen"
        redis_client.lpush(target_queue, json.dumps(scene_data))
        
        return {
            "status": "success", 
            "message": f"Scene {scene_file_name} pushed to {target_queue}"
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
