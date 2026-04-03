#!/usr/bin/env python3
"""
Unlock Pipeline - Sblocca le code Redis e pulisce i registri per un progetto specifico.
Utile per far ripartire un benchmark da zero senza rimasugli di test precedenti.
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence

def unlock_project(project_name: str, host: str = None):
    host = host or os.getenv("REDIS_HOST", "localhost")
    print(f"🧹 Pulizia Redis per il progetto: {project_name} su {host}...")
    
    # Override host for the factory
    os.environ["REDIS_HOST"] = host
    redis = get_redis_client()
    persistence = DiasPersistence()
    clean_title = persistence.normalize_id(project_name)
    
    # 1. Registro DIAS (Hash)
    registry_key = f"dias:registry:{clean_title}"
    if redis.client.exists(registry_key):
        redis.client.delete(registry_key)
        print(f"  ✅ Registro eliminato: {registry_key}")
    
    # 2. Checkpoint DIAS
    checkpoint_key = f"dias:checkpoint:{clean_title}"
    if redis.client.exists(checkpoint_key):
        redis.client.delete(checkpoint_key)
        print(f"  ✅ Checkpoint eliminato: {checkpoint_key}")
        
    # 3. Controllo Semaphori e Status
    keys_to_del = redis.client.keys(f"dias:control:{clean_title}:*")
    if keys_to_del:
        redis.client.delete(*keys_to_del)
        print(f"  ✅ Eliminati {len(keys_to_del)} semafori di controllo.")
        
    # 4. Gateway Mailbox (Pulisce i risultati AI pendenti/cacheati)
    # Cerchiamo i job ID che iniziano con 'job-' e appartengono al Gateway ARIA per DIAS
    # Nota: I job deterministici di Stage B sono job-d4ff...
    mailbox_keys = redis.client.keys("aria:c:dias:job-*")
    if mailbox_keys:
        # In un sistema multi-progetto bisognerebbe filtrare, 
        # ma qui di solito lavoriamo a un benchmark alla volta.
        # Filtriamo per sicurezza? No, meglio sbloccare tutto il mailbox dias se richiesto.
        redis.client.delete(*mailbox_keys)
        print(f"  ✅ Svuotate {len(mailbox_keys)} mailbox del Gateway ARIA per il client 'dias'.")
        
    # 5. Code di input (opzionale - se vogliamo svuotare i task non ancora presi)
    # Le code sono condivise, quindi non le svuotiamo interamente se ci sono altri progetti.
    # Tuttavia, il resume le ri-popola correttamente.
    
    print(f"✨ Progetto '{project_name}' sbloccato con successo.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unlock DIAS Pipeline for a project")
    parser.add_argument("project_id", help="ID o nome del progetto (es: Cronache-del-Silicio)")
    parser.add_argument("--host", default=None, help="Indirizzo del server Redis (default: env REDIS_HOST o localhost)")
    
    args = parser.parse_args()
    unlock_project(args.project_id, host=args.host)
