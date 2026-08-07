import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

class ClickUpClient:
    def __init__(self):
        token = str(os.getenv("CLICKUP_API_TOKEN") or "").strip("\"'")
        self.headers = {"Authorization": token}
        self.base_url = "https://api.clickup.com/api/v2"


    def _get(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        retries = 15
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                if response.status_code == 429:
                    wait = min(5 * (attempt + 1), 60)
                    print(f"Rate limit atingido. Aguardando {wait}s...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError:
                print(f"Erro HTTP {response.status_code} na requisição ({endpoint}): {response.text}")
                if attempt == retries - 1:
                    return None
                time.sleep(5)
            except requests.exceptions.RequestException as e:
                print(f"Erro de Conexão ({endpoint}): {e}")
                if attempt == retries - 1:
                    return None
                time.sleep(2)
        return None

    def _get_all(self, endpoint, key):
        """Busca itens ativos e arquivados combinando os dois resultados."""
        active = self._get(endpoint, params={"archived": "false"}) or {}
        archived = self._get(endpoint, params={"archived": "true"}) or {}
        return active.get(key, []) + archived.get(key, [])

    def get_teams(self):
        data = self._get("team")
        return data.get("teams", []) if data else []

    def get_spaces(self, team_id):
        return self._get_all(f"team/{team_id}/space", "spaces")

    def get_folders(self, space_id):
        return self._get_all(f"space/{space_id}/folder", "folders")

    def get_lists_in_space(self, space_id):
        return self._get_all(f"space/{space_id}/list", "lists")

    def get_lists_in_folder(self, folder_id):
        return self._get_all(f"folder/{folder_id}/list", "lists")

    def get_tasks(self, list_id, subtasks=True, date_updated_gt=None):
        """Extrai todas as tarefas de uma lista, incluindo fechadas, arquivadas e subtarefas."""
        all_tasks = []
        seen_ids = set()

        for archived in ("false", "true"):
            page_index = 0
            while True:
                params = {
                    "page": page_index,
                    "subtasks": "true" if subtasks else "false",
                    "include_closed": "true",
                    "archived": archived,
                }
                if date_updated_gt:
                    params["date_updated_gt"] = date_updated_gt

                data = self._get(f"list/{list_id}/task", params=params)
                if not isinstance(data, dict):
                    break

                page_tasks = data.get("tasks")
                if not page_tasks or not isinstance(page_tasks, list):
                    break

                for task in page_tasks:
                    tid = task.get("id")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        all_tasks.append(task)

                if len(page_tasks) < 100:
                    break
                page_index += 1

        return all_tasks

    def get_task_comments(self, task_id):
        data = self._get(f"task/{task_id}/comment")
        return data.get("comments", []) if data else []

    def get_shared_items(self, team_id):
        data = self._get(f"team/{team_id}/shared")
        if data and "shared" in data:
            return data["shared"]
        return {"folders": [], "lists": [], "tasks": []}

    def get_task(self, task_id):
        return self._get(f"task/{task_id}")

    def get_team_views(self, team_id):
        data = self._get(f"team/{team_id}/view")
        return (data or {}).get("views", [])

    def get_space_views(self, space_id):
        data = self._get(f"space/{space_id}/view")
        return (data or {}).get("views", [])

    def get_folder_views(self, folder_id):
        data = self._get(f"folder/{folder_id}/view")
        return (data or {}).get("views", [])

    def get_list_views(self, list_id):
        data = self._get(f"list/{list_id}/view")
        return (data or {}).get("views", [])

    def get_view_tasks(self, view_id):
        """Retorna todas as tarefas visíveis em uma view específica."""
        all_tasks = []
        seen_ids = set()
        page_index = 0
        while True:
            data = self._get(f"view/{view_id}/task", params={"page": page_index})
            if not isinstance(data, dict):
                break
            page_tasks = data.get("tasks") or []
            for task in page_tasks:
                tid = task.get("id")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    all_tasks.append(task)
            if not page_tasks:
                break
            page_index += 1
        return all_tasks

    def get_time_in_status(self, task_id: str) -> dict:
        """Retorna dados de tempo por status de uma tarefa."""
        url = f"{self.base_url}/task/{task_id}/time_in_status"
        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}
