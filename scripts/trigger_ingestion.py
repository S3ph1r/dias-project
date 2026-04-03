#!/usr/bin/env python3
import json
import uuid
import argparse
from pathlib import Path
from src.common.redis_factory import get_redis_client

def trigger(file_path, project_id):
    abs_path = str(Path(file_path).absolute())
    print(f"🚀 Triggering ingestion for: {abs_path}")
    
    redis = get_redis_client()
    
    # Message format for dias:q:0:upload
    message = {
        "book_id": project_id,
        "title": project_id.replace("-", " "),
        "file_path": abs_path,
        "original_filename": Path(file_path).name,
        "author": "User",
        "force": True
    }
    
    redis.client.rpush("dias:q:0:upload", json.dumps(message))
    print(f"✅ Message sent to dias:q:0:upload for project '{project_id}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to PDF/EPUB file")
    parser.add_argument("--id", default="Cronache-del-Silicio", help="Project ID")
    args = parser.parse_args()
    
    trigger(args.file, args.id)
