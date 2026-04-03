#!/usr/bin/env python3
"""
Test Stage A con persistenza file-based
"""

import sys
import os
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.stages.stage_a_text_ingester import TextIngester
from src.common.config import get_config
from src.common.redis_factory import get_redis_client
import logging

def test_stage_a_persistence():
    """Test Stage A con salvataggio su disco"""
    
    # Configurazione
    config = get_config()
    redis_client = get_redis_client()
    
    # Inizializza Stage A
    ingester = TextIngester(redis_client, config)
    
    # Test con un piccolo testo
    test_content = """
    Questo è un testo di esempio per verificare il funzionamento di Stage A con persistenza.
    Il testo deve essere abbastanza lungo per essere suddiviso in blocchi.
    
    Possiamo aggiungere più paragrafi per testare la coerenza narrativa.
    Ogni blocco dovrebbe mantenere i confini dei paragrafi quando possibile.
    
    Questo è un altro paragrafo che serve per aumentare la lunghezza del testo.
    Vogliamo assicurarci che il sistema crei blocchi di dimensioni adeguate.
    
    Continuiamo ad aggiungere contenuto per testare il chunking intelligente.
    Il sistema dovrebbe rispettare i confini naturali del testo quando li trova.
    """
    
    # Crea file di test temporaneo
    test_file = Path(__file__).parent / "test_book.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    try:
        print(f"🧪 Testing Stage A con file: {test_file}")
        
        # Processa il libro
        book_id = "test_book_001"
        metadata = {
            "title": "Libro di Test",
            "author": "Test Author"
        }
        
        blocks = ingester.process_book_file(test_file, book_id, metadata)
        
        print(f"✅ Stage A completato!")
        print(f"📊 Risultati:")
        print(f"   - Blocchi creati: {len(blocks)}")
        
        if blocks:
            for i, block in enumerate(blocks):
                print(f"   - Blocco {i+1}: {block.word_count} parole")
                print(f"     ID: {block.block_id}")
                print(f"     Testo preview: {block.block_text[:100]}...")
                print()
        
        # Verifica persistenza
        print(f"💾 Verificando persistenza su disco...")
        data_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
        
        if data_dir.exists():
            files = list(data_dir.glob(f"{book_id}_*.json"))
            print(f"   - File salvati: {len(files)}")
            
            for file in files:
                print(f"   - {file.name}")
                
                # Leggi e verifica contenuto
                import json
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"     ✓ Book ID: {data.get('book_id')}")
                    print(f"     ✓ Block ID: {data.get('block_id')}")
                    print(f"     ✓ Word count: {data.get('word_count')}")
                    print(f"     ✓ Text length: {len(data.get('block_text', ''))} chars")
        
        print(f"\n🎉 Test completato con successo!")
        
    except Exception as e:
        print(f"❌ Errore durante il test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Pulizia
        if test_file.exists():
            test_file.unlink()

if __name__ == "__main__":
    test_stage_a_persistence()