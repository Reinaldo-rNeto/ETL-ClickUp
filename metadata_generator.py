"""
metadata_generator.py — Gera o JSON de metadados das colunas do CSV extraído.
Usado para cadastro no conjunto de dados do BigData PE.
"""

import re
import json
import os

# Tipos inferidos por padrão de nome de coluna
_SUFFIXES_DATE = {"(date)", "(data)"}
_SUFFIXES_INT  = {"(number)", "(integer)", "(int)"}

_DESCRICOES_PADRAO = {
    "Task Type":                    "Tipo da tarefa no ClickUp",
    "Task ID":                      "Identificador único da tarefa",
    "Task Name":                    "Nome da tarefa",
    "Status":                       "Status atual da tarefa",
    "Task Content":                 "Descrição/conteúdo da tarefa",
    "Assignee":                     "Responsável(is) pela tarefa",
    "Priority":                     "Prioridade da tarefa",
    "Latest Comment":               "Último comentário registrado",
    "Comment Count":                "Quantidade total de comentários",
    "Assigned Comment Count":       "Quantidade de comentários atribuídos",
    "Due Date":                     "Data de vencimento",
    "Start Date":                   "Data de início",
    "Date Created":                 "Data de criação da tarefa",
    "Date Updated":                 "Data da última atualização",
    "Date Closed":                  "Data de encerramento",
    "Date Done":                    "Data de conclusão",
    "Created By":                   "Usuário que criou a tarefa",
    "Space":                        "Espaço do ClickUp onde a tarefa está",
    "Folder":                       "Pasta dentro do espaço",
    "List":                         "Lista/View de origem da tarefa",
    "Subtask ID's":                 "IDs das subtarefas vinculadas",
    "Subtask URL's":                "URLs das subtarefas vinculadas",
    "tags":                         "Etiquetas associadas à tarefa",
    "Lists":                        "Listas adicionais onde a tarefa aparece",
    "Sprints":                      "Sprints associados",
    "Linked Tasks":                 "Tarefas vinculadas",
    "Linked Docs":                  "Documentos vinculados",
    "Time Logged":                  "Tempo registrado na tarefa",
    "Time Logged Rolled Up":        "Tempo registrado acumulado (subtarefas)",
    "Time Estimate":                "Estimativa de tempo",
    "Time Estimate Rolled Up":      "Estimativa de tempo acumulada (subtarefas)",
    "Points Estimate":              "Pontos estimados",
    "Points Estimate Rolled Up":    "Pontos estimados acumulados (subtarefas)",
}


def _normalizar_mapeamento(nome: str) -> str:
    """Converte nome da coluna em nome de atributo normalizado (snake_case)."""
    # Remove sufixo de tipo entre parênteses: "Nome (drop down)" → "Nome"
    nome = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
    # Remove emojis e caracteres especiais
    nome = re.sub(r"[^\w\s]", "", nome, flags=re.UNICODE)
    # Converte para snake_case
    nome = nome.strip().lower()
    nome = re.sub(r"\s+", "_", nome)
    nome = re.sub(r"_+", "_", nome)
    return nome or "campo"


def _inferir_tipo(nome: str) -> str:
    """Infere o tipo de dado a partir do nome da coluna. Valores: TEXTO, NUMERO, DATA."""
    nome_lower = nome.lower()

    # Sufixo de tipo explícito entre parênteses
    match = re.search(r"\(([^)]+)\)$", nome_lower)
    if match:
        sufixo = f"({match.group(1).strip()})"
        if sufixo in _SUFFIXES_DATE:
            return "DATA"
        if sufixo in _SUFFIXES_INT:
            return "NUMERO"

    # Palavras-chave de data no nome
    if any(k in nome_lower for k in ("date", "data", "inicio", "início", "término", "termino", "vencimento", "realização")):
        return "DATA"

    # Palavras-chave numéricas no nome
    if any(k in nome_lower for k in ("count", "quantidade", "qtd", "points", "pontos")):
        return "NUMERO"

    return "TEXTO"


def _inferir_descricao(nome: str) -> str:
    """Retorna descrição padrão ou gera uma genérica."""
    if nome in _DESCRICOES_PADRAO:
        return _DESCRICOES_PADRAO[nome]
    if nome.startswith("[TIS]"):
        status = nome.replace("[TIS]", "").strip()
        return f"Tempo total que a tarefa permaneceu no status '{status}'"
    # Remove sufixo de tipo para descrever
    base = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
    return f"Campo customizado: {base}"


def gerar_metadados(colunas: list[str], output_path: str) -> str:
    """
    Gera o arquivo JSON de metadados para o BigData PE.

    Args:
        colunas: lista de nomes de colunas do CSV
        output_path: pasta onde salvar o arquivo

    Returns:
        Caminho do arquivo gerado
    """
    metadados = []
    for col in colunas:
        metadados.append({
            "campo":      col,
            "descricao":  _inferir_descricao(col),
            "mapeamento": _normalizar_mapeamento(col),
            "tipo":       _inferir_tipo(col),
            "categoria":  "DADO COMUM",
        })

    os.makedirs(output_path, exist_ok=True)
    arquivo = os.path.join(output_path, "metadados_ProjetosGPD.json")
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(metadados, f, ensure_ascii=False, indent=2)

    print(f"  [Metadados] {len(metadados)} colunas -> {arquivo}")
    return arquivo


def gerar_metadados_do_csv(csv_path: str) -> str:
    """Lê as colunas de um CSV existente e gera o JSON de metadados."""
    import csv
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        colunas = next(reader)
    output_dir = os.path.dirname(csv_path)
    return gerar_metadados(colunas, output_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python metadata_generator.py <caminho_do_csv>")
        sys.exit(1)
    resultado = gerar_metadados_do_csv(sys.argv[1])
    print(f"Gerado: {resultado}")
