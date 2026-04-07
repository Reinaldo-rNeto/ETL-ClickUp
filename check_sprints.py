import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("CLICKUP_API_TOKEN", "").strip()
if TOKEN.startswith('"'): TOKEN = TOKEN[1:-1]
elif TOKEN.startswith("'"): TOKEN = TOKEN[1:-1]
headers = {"Authorization": TOKEN}

url = "https://api.clickup.com/api/v2/team/9013340838/shared"
data = requests.get(url, headers=headers).json()

shared = data.get("shared", {})
for f in shared.get("folders", []):
    print(f"Folder Compartilhado: {f['name']}")
    url_lists = f"https://api.clickup.com/api/v2/folder/{f['id']}/list"
    lists_resp = requests.get(url_lists, headers=headers).json()
    for lst in lists_resp.get("lists", []):
        print(f"  -> Lista: {lst['name']}")
