import requests
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

resp = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {api_key}"}
)

print("=== MODEL FREE ===")
for m in resp.json()["data"]:
    price = m.get("pricing", {}).get("prompt", "?")
    if price == "0":
        print(m["id"])