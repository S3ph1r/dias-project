#!/usr/bin/env python3
"""
Test Stage A con "Cronache di Silicio" - PDF reale
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

def test_cronache_silicio():
    """Test Stage A con Cronache di Silicio PDF"""
    
    # Configurazione
    config = get_config()
    redis_client = get_redis_client()
    
    # Inizializza Stage A
    ingester = TextIngester(redis_client, config)
    
    # Percorso del PDF
    pdf_path = "/home/Projects/NH-Mini/sviluppi/dias/tests/fixtures/cronache_silicio_real_book.pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ PDF non trovato: {pdf_path}")
        return
    
    try:
        print(f"📖 Processando 'Cronache di Silicio'...")
        print(f"📁 File: {pdf_path}")
        print(f"📊 Dimensione: {Path(pdf_path).stat().st_size / 1024 / 1024:.1f} MB")
        
        # Processa il libro
        book_id = "cronache_silicio_001"
        metadata = {
            "title": "Cronache di Silicio",
            "author": "Autore Sconosciuto"
        }
        
        print(f"\n🔄 Avvio processing...")
        blocks = ingester.process_book_file(pdf_path, book_id, metadata)
        
        print(f"\n✅ Stage A completato!")
        print(f"📊 Risultati:")
        print(f"   - Blocchi creati: {len(blocks)}")
        
        if blocks:
            total_words = sum(block.word_count for block in blocks)
            avg_words = total_words // len(blocks) if blocks else 0
            
            print(f"   - Parole totali: {total_words:,}")
            print(f"   - Media parole/blocco: {avg_words:,}")
            print(f"   - Range parole/blocco: {min(b.word_count for b in blocks)} - {max(b.word_count for b in blocks)}")
            
            print(f"\n📋 Dettagli blocchi:")
            for i, block in enumerate(blocks[:3]):  # Mostra primi 3 blocchi
                print(f"   - Blocco {i+1}: {block.word_count} parole")
                print(f"     ID: {block.block_id}")
                print(f"     Indice: {block.block_index}/{block.total_blocks_in_chapter}")
                print(f"     Testo preview: {block.block_text[:150]}...")
                print()
            
            if len(blocks) > 3:
                print(f"   ... e altri {len(blocks) - 3} blocchi")
        
        # Verifica persistenza
        print(f"\n💾 Verificando persistenza su disco...")
        data_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
        
        if data_dir.exists():
            files = list(data_dir.glob(f"{book_id}_*.json"))
            print(f"   - File salvati: {len(files)}")
            
            if files:
                # Mostra info sul primo file
                first_file = files[0]
                import json
                with open(first_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"   - Esempio file: {first_file.name}")
                    print(f"     ✓ Book ID: {data.get('book_id')}")
                    print(f"     ✓ Block ID: {data.get('block_id')}")
                    print(f"     ✓ Word count: {data.get('word_count')}")
                    print(f"     ✓ Text length: {len(data.get('block_text', ''))} chars")
                    print(f"     ✓ Block index: {data.get('block_index')}/{data.get('total_blocks_in_chapter')}")
        
        print(f"\n🎉 Test 'Cronache di Silicio' completato con successo!")
        
        # Ora possiamo testare Stage B con uno di questi blocchi reali
        if blocks:
            print(f"\n💡 Suggerimento: Ora puoi testare Stage B con uno di questi blocchi reali!")
            print(f"   Usa il Block ID: {blocks[0].block_id}")
        
    except Exception as e:
        print(f"❌ Errore durante il processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cronache_silicio()