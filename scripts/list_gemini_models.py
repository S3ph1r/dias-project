import os
import json
from google import genai
from dotenv import load_dotenv

def list_models():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in .env")
        return

    try:
        client = genai.Client(api_key=api_key)
        print("Fetching models from Google Gemini API...")
        models = client.models.list()
        
        print("\nAvailable Models:")
        print("-" * 50)
        for m in models:
            # Filter for Flash and Lite models
            if "flash" in m.name.lower() or "lite" in m.name.lower():
                print(f"ID: {m.name: <40} | Name: {m.display_name}")
        print("-" * 50)
        
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_models()
