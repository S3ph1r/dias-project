import os
import requests
import json
from dotenv import load_dotenv

def list_models():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"Found {len(models)} models:")
            # Sort by name for readability
            models.sort(key=lambda x: x["name"])
            for m in models:
                name = m["name"].replace("models/", "")
                display_name = m.get("displayName", "N/A")
                description = m.get("description", "N/A")
                print(f"- {name:40} | {display_name}")
        else:
            print(f"Error: API returned {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    list_models()
