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
    """Converte nome da coluna em nome de atributo normalizado (snake_case ASCII)."""
    import unicodedata
    # Remove sufixo de tipo entre parênteses: "Nome (drop down)" → "Nome"
    nome = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
    # Remove emojis e caracteres especiais
    nome = re.sub(r"[^\w\s]", "", nome, flags=re.UNICODE)
    # Converte para snake_case
    nome = nome.strip().lower()
    nome = re.sub(r"\s+", "_", nome)
    # Normaliza acentos para ASCII
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    nome = re.sub(r"[^\w]", "_", nome)
    nome = re.sub(r"_+", "_", nome).strip("_")
    return nome or "campo"


_FALSOS_POSITIVOS_DATA = {
    "data center",
}

def _inferir_tipo(nome: str) -> str:
    """Infere o tipo de dado a partir do nome da coluna. Valores: TEXTO, NUMERO, DATA."""
    nome_lower = nome.lower()

    # Sufixo de tipo explícito entre parênteses (mais confiável — usar primeiro)
    match = re.search(r"\(([^)]+)\)$", nome_lower)
    if match:
        sufixo = f"({match.group(1).strip()})"
        if sufixo in _SUFFIXES_DATE:
            return "DATA"
        if sufixo in _SUFFIXES_INT:
            return "NUMERO"

    # Ignora falsos positivos antes de checar palavras-chave de data
    if any(fp in nome_lower for fp in _FALSOS_POSITIVOS_DATA):
        return "TEXTO"

    # Palavras-chave de data no nome (sem sufixo explícito)
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
    Formato: {"metadata": [{chave, data, campo, descricao, mapeamentoCampo, tipo, mascara, categoria}]}
    """
    metadados = []
    mapeamentos_vistos: dict[str, int] = {}
    for col in colunas:
        base_map = _normalizar_mapeamento(col)
        if base_map in mapeamentos_vistos:
            mapeamentos_vistos[base_map] += 1
            mapeamento = f"{base_map}_{mapeamentos_vistos[base_map]}"
        else:
            mapeamentos_vistos[base_map] = 1
            mapeamento = base_map

        tipo_interno = _inferir_tipo(col)
        # BigData PE usa "NÚMERO" (com acento) e o tipo DATA controla o campo "data"
        tipo_bd = "NÚMERO" if tipo_interno == "NUMERO" else tipo_interno
        mascara = "Inteiro" if tipo_interno == "NUMERO" else ""
        is_chave = mapeamento == "task_id"
        is_data  = tipo_interno == "DATA"

        metadados.append({
            "chave":          is_chave,
            "data":           is_data,
            "campo":          mapeamento,
            "descricao":      _inferir_descricao(col),
            "mapeamentoCampo": "",
            "tipo":           tipo_bd,
            "mascara":        mascara,
            "categoria":      "DADO COMUM",
        })

    os.makedirs(output_path, exist_ok=True)
    arquivo = os.path.join(output_path, "metadados_ProjetosGPD.json")
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadados}, f, ensure_ascii=False, indent=2)

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
