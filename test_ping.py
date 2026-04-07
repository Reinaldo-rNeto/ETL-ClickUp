import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("CLICKUP_API_TOKEN", "")
# Remove aspas se o usuário colou com aspas ao redor
if TOKEN.startswith('"') and TOKEN.endswith('"'):
    TOKEN = TOKEN[1:-1]
elif TOKEN.startswith("'") and TOKEN.endswith("'"):
    TOKEN = TOKEN[1:-1]

if not TOKEN.startswith("pk_") and not TOKEN.startswith("pk_"):
    print(f"O Token ({TOKEN[:5]}...) não parece estar no formato correto (pk_...). O ClickUp usa 'pk_' para Personal Tokens.")

headers = {
    "Authorization": TOKEN
}
url = "https://api.clickup.com/api/v2/team"

try:
    print("Tentando conectar com o ClickUp...")
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        teams = data.get("teams", [])
        print(f"SUCESSO! Token super válido! 🎉")
        print(f"Encontramos {len(teams)} Workspace(s):")
        for team in teams:
            print(f" -> [{team['id']}] {team['name']}")
    else:
        print(f"ERRO DE AUTENTICAÇÃO: {response.status_code}")
        print(f"Resposta do servidor: {response.text}")
except Exception as e:
    print(f"Erro ao rodar script: {e}")
