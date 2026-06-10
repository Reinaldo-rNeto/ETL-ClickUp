import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("CLICKUP_API_TOKEN", "").strip()
if TOKEN.startswith('"'): TOKEN = TOKEN[1:-1]
elif TOKEN.startswith("'"): TOKEN = TOKEN[1:-1]
headers = {"Authorization": TOKEN}

task_id = "86a7b1ckm"
task_url = f"https://api.clickup.com/api/v2/task/{task_id}"
task = requests.get(task_url, headers=headers).json()
list_id = task.get('list', {}).get('id')

if list_id:
    tasks_url = f"https://api.clickup.com/api/v2/list/{list_id}/task?subtasks=true&include_closed=true"
    tasks = requests.get(tasks_url, headers=headers).json().get("tasks", [])
    
    subtasks = [t for t in tasks if t.get("parent") == task_id]
    print(f"Found {len(subtasks)} subtasks inside List {list_id} for parent {task_id}")
    if subtasks:
        print(f"Exemplo de Subtarefa (ID: {subtasks[0].get('id')}): parent={subtasks[0].get('parent')}")
else:
    print("Nao consegui acessar a Lista da tarefa.")
