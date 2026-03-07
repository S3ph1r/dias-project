import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.stages.stage_c_scene_director import SceneDirector
from src.common.config import get_config

def main():
    print("🚀 DIAS Stage C - Phase 5 Verification")
    print("Testing: Dynamic Emotional Beats + Number Normalization")
    
    # Setup
    config = get_config()
    
    # Path del chunk di input (Stage B)
    base_data = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output")
    input_file = base_data / "test_cronache_b6266202-3853-4a1e-93b8-b8c92eee3707_20260305_003907.json"
    
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return

    print(f"[*] Loading input: {input_file.name}")
    with open(input_file, 'r', encoding='utf-8') as f:
        item = json.load(f)
    
    # Inizializza SceneDirector
    # NB: SceneDirector caricherà i dati necessari tramite persistence
    director = SceneDirector()
    
    # Esegui process_item (Logica nuova)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[*] Calling SceneDirector.process_item (Gemini dynamic call)...")
    
    result = director.process_item(item)
    
    if result and result.get("scenes"):
        scenes = result["scenes"]
        print(f"✅ Success! Generated {len(scenes)} dynamic scenes.")
        
        # Salvataggio per versioning qualitativo
        output_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_c/test_runs")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"test_phase5_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"[*] Result saved to: {output_file}")
        
        # Verifica veloce dei requisiti
        found_normalized_number = False
        sample_text = ""
        
        for i, scene in enumerate(scenes):
            text = scene.get("text_content", "")
            sample_text += text + " "
            instruct = scene.get("qwen3_instruct", "")
            label = scene.get("scene_label", "N/A")
            
            print(f"\n--- SCENA {i} [{label}] ---")
            print(f"Instruct: {instruct}")
            print(f"Text Preview: {text[:150]}...")
            
            # Controllo manuale rapido via script
            if "duemilaquarantadue" in text.lower() or "duemila" in text.lower():
                found_normalized_number = True
        
        print("\n" + "="*50)
        if found_normalized_number:
            print("✨ VERIFICA NUMERI: OK (Trovata espansione 'duemilaquarantadue')")
        else:
            print("⚠️ VERIFICA NUMERI: NON RILEVATA (Controllare manualmente nel JSON)")
            
        if len(scenes) > 1:
            print(f"✨ VERIFICA SEGMENTAZIONE: OK ({len(scenes)} scene dinamiche)")
        else:
            print("⚠️ VERIFICA SEGMENTAZIONE: Blocco unico (Gemini non ha diviso il testo)")
        print("="*50)
        
    else:
        print("❌ Stage C failed to produce results.")

if __name__ == "__main__":
    main()
