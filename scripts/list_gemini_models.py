import os
import json
import google.genai as genai
from dotenv import load_dotenv

def list_models():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY not found")
        return

    client = genai.Client(api_key=api_key)
    try:
        print("Attempting to list models...")
        # Note: In the new google-genai SDK, listing models might vary by version
        # We can also try a simple generation with a known safe name like 'gemini-1.5-flash'
        # but let's see if we can discover.
        for model in client.models.list():
            print(f"Model: {model.name} (Supported actions: {model.supported_actions})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
