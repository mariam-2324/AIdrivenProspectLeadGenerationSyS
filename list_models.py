import os
import requests
from dotenv import load_dotenv

load_dotenv()
r = requests.get(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    params={"pageSize": 100},
    timeout=20,
)
r.raise_for_status()
for m in r.json()["models"]:
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print(m["name"].replace("models/", ""))

        # gemini-3.5-flash