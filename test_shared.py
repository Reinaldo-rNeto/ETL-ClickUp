import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()
TOKEN = os.getenv("CLICKUP_API_TOKEN", "").strip()
if TOKEN.startswith('"') and TOKEN.endswith('"'): TOKEN = TOKEN[1:-1]
elif TOKEN.startswith("'") and TOKEN.endswith("'"): TOKEN = TOKEN[1:-1]

headers = {"Authorization": TOKEN}
team_id = "9013340838" # Conforme o log anterior

url = f"https://api.clickup.com/api/v2/team/{team_id}/shared"
resp = requests.get(url, headers=headers)

if resp.status_code == 200:
    data = resp.json()
    print("Itens Compartilhados Encontrados:")
    shared = data.get("shared", {})
    
    folders = shared.get("folders", [])
    print(f"- Folders: {len(folders)}")
    for f in folders:
        print(f"  * {f['name']} (ID: {f['id']})")
        
    lists = shared.get("lists", [])
    print(f"- Lists: {len(lists)}")
    for l in lists:
        print(f"  * {l['name']} (ID: {l['id']})")
        
    tasks = shared.get("tasks", [])
    print(f"- Tasks Diretas: {len(tasks)}")
    for t in tasks:
        print(f"  * {t['name']} (ID: {t['id']})")
else:
    print(f"Erro: {resp.status_code} - {resp.text}")
