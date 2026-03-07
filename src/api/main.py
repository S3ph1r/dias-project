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
    projects_dir = Path(config.base_dir) / "data" / "stage_a" / "output"
    if not projects_dir.exists():
        return []
    
    projects = []
    # Simple logic: each unique book title found in filenames
    # Pattern: book_id-chunk_id-scene_id-timestamp.json
    found_titles = set()
    for file in projects_dir.glob("*.json"):
        # Format: Cronache-del-Silicio-chunk-000-20260307_005036.json
        parts = file.stem.split("-chunk-")
        if len(parts) > 0:
            title = parts[0]
            if title not in found_titles:
                found_titles.add(title)
                projects.append({
                    "id": title,
                    "name": title.replace("-", " "),
                    "last_modified": datetime.datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                })
    
    return projects

@app.get("/projects/{project_id}")
async def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Detailed progress for a specific book.
    Calculates progress by comparing file counts across stages A through G.
    """
    base_path = Path(config.base_dir) / "data"
    stages = ["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f", "stage_g"]
    
    stats = {}
    total_chunks = 0
    
    # 1. Count Stage A files to determine total chunks
    stage_a_dir = base_path / "stage_a" / "output"
    stage_a_files = list(stage_a_dir.glob(f"{project_id}-chunk-*.json"))
    total_chunks = len(stage_a_files)
    stats["stage_a"] = {"count": total_chunks, "status": "done" if total_chunks > 0 else "pending"}

    # 2. Check other stages
    # Note: Stage C produces multiple scenes per chunk, but here we count chunk-level completeness
    for stage in stages[1:]:
        stage_dir = base_path / stage / "output"
        if not stage_dir.exists():
            stats[stage] = {"count": 0, "status": "pending"}
            continue
            
        found_files = list(stage_dir.glob(f"{project_id}-*"))
        stats[stage] = {
            "count": len(found_files),
            "status": "in_progress" if 0 < len(found_files) < total_chunks else ("done" if len(found_files) >= total_chunks else "pending")
        }

    # 3. Calculate overall percentage (simplified)
    # This is a guestimate: Weighting stages differently or counting actual scene completion would be better
    completed_stages = sum(1 for s in stats.values() if s["status"] == "done")
    progress_pct = (completed_stages / len(stages)) * 100

    return {
        "project_id": project_id,
        "total_chunks": total_chunks,
        "stages": stats,
        "overall_progress": round(progress_pct, 2)
    }

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
    output_dir = Path(config.base_dir) / "data" / "stage_d" / "output"
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
