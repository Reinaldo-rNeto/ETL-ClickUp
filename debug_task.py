import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("CLICKUP_API_TOKEN", "").strip()
if TOKEN.startswith('"'): TOKEN = TOKEN[1:-1]
elif TOKEN.startswith("'"): TOKEN = TOKEN[1:-1]
headers = {"Authorization": TOKEN}

task_id = "86a7b1ckm"

url = f"https://api.clickup.com/api/v2/task/{task_id}"
resp = requests.get(url, headers=headers).json()
print("=== TASK ===")
print(f"Nome: {resp.get('name')}")
print(f"Anexos na Task: {len(resp.get('attachments', []))}")

url_c = f"https://api.clickup.com/api/v2/task/{task_id}/comment"
comments = requests.get(url_c, headers=headers).json().get("comments", [])
print(f"\n=== COMMENTS ({len(comments)}) ===")
if comments:
    print(json.dumps(comments[0], indent=2))
