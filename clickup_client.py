import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

class ClickUpClient:
    def __init__(self):
        token = os.getenv("CLICKUP_API_TOKEN") or ""
        token = str(token).strip("\"'") # Remove aspas com segurança

            
        self.headers = {
            "Authorization": token
        }
        self.base_url = "https://api.clickup.com/api/v2"

    def _get(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        retries = 3
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, params=params)
                if response.status_code == 429: # Trata Rate Limit do ClickUp (100req/min)
                    print("Rate limit atingido. Aguardando...")
                    time.sleep(2)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                print(f"Erro HTTP {response.status_code} na requisição ({endpoint}): {response.text}")
                if attempt == retries - 1:
                    return None
                time.sleep(2)
            except requests.exceptions.RequestException as e:
                print(f"Erro de Conexão ({endpoint}): {e}")
                if attempt == retries - 1:
                    return None
                time.sleep(2)
        return None

    def get_teams(self):
        """Lista os Workspaces (Teams)"""
        data = self._get("team")
        return data.get("teams", []) if data else []

    def get_spaces(self, team_id):
        """Lista os Espaços dentro do Workspace"""
        data = self._get(f"team/{team_id}/space")
        return data.get("spaces", []) if data else []

    def get_folders(self, space_id):
        """Lista as Pastas dentro de um Espaço"""
        data = self._get(f"space/{space_id}/folder")
        return data.get("folders", []) if data else []

    def get_lists_in_space(self, space_id):
        """Lista as Listas que ficam soltas na raiz do Espaço (Sem Pasta)"""
        data = self._get(f"space/{space_id}/list")
        return data.get("lists", []) if data else []

    def get_lists_in_folder(self, folder_id):
        """Lista as Listas dentro de uma Pasta"""
        data = self._get(f"folder/{folder_id}/list")
        return data.get("lists", []) if data else []

    def get_tasks(self, list_id, subtasks=True, date_updated_gt=None):
        """Extrai todas as tarefas de uma lista, incluindo arquivadas e as subtarefas (se passado subtasks=True)"""
        tasks = []
        page_index = 0
        while True:
            params = {
                "page": page_index,
                "subtasks": "true" if subtasks else "false",
                "include_closed": "true"
            }
            if date_updated_gt:
                params["date_updated_gt"] = date_updated_gt
                
            data = self._get(f"list/{list_id}/task", params=params)
            
            if not isinstance(data, dict):
                break
                
            page_tasks = data.get("tasks")
            if not page_tasks or not isinstance(page_tasks, list):
                break
                
            tasks.extend(page_tasks)
            
            # ClickUp retorna máximo de 100 tarefas por página (se for menor, acabou)
            if len(page_tasks) < 100:
                break
                
            page_index = page_index + 1

            
        return tasks

    def get_task_comments(self, task_id):
        """Extrai todo o histórico de comentários de uma tarefa específica"""
        data = self._get(f"task/{task_id}/comment")
        return data.get("comments", []) if data else []

    def get_shared_items(self, team_id):
        """Lista as Pastas, Listas e Tarefas que foram compartilhadas diretamente com o usuário"""
        data = self._get(f"team/{team_id}/shared")
        if data and "shared" in data:
            return data["shared"]
        return {"folders": [], "lists": [], "tasks": []}
        
    def get_task(self, task_id):
        """Busca os dados de uma única tarefa (Usado para pescar tarefas-pai perdidas nos filtros)"""
        return self._get(f"task/{task_id}")
