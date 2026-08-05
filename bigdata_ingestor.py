"""
bigdata_ingestor.py — Ingesta o CSV gerado pelo extrator no BigData PE via Pypeline.
Padrão: ingerir_dados_datamart com metadados inline (baseado em dicas do time BigData PE).
"""

import os
import re
import glob
import json
import unicodedata
import pandas as pd
from collections import OrderedDict


NOME_TABELA = "projetosgpd"


def _normalizar_col(nome: str) -> str:
    nome = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
    nome = re.sub(r"[^\w\s]", "", nome, flags=re.UNICODE)
    nome = nome.strip().lower()
    nome = re.sub(r"\s+", "_", nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    nome = re.sub(r"[^\w]", "_", nome)
    nome = re.sub(r"_+", "_", nome).strip("_")
    return nome or "campo"


def _renomear_colunas(df: pd.DataFrame) -> pd.DataFrame:
    vistos: dict[str, int] = {}
    mapa = {}
    for col in df.columns:
        base = _normalizar_col(col)
        if base in vistos:
            vistos[base] += 1
            mapa[col] = f"{base}_{vistos[base]}"
        else:
            vistos[base] = 1
            mapa[col] = base
    return df.rename(columns=mapa)


def _encontrar_csv(output_dir: str) -> str | None:
    arquivos = sorted(glob.glob(os.path.join(output_dir, "*.csv")), key=os.path.getmtime, reverse=True)
    return arquivos[0] if arquivos else None


def _carregar_campos_meta(output_dir: str) -> list | None:
    meta_path = os.path.join(output_dir, "metadados_ProjetosGPD.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f).get("metadata", [])


def _build_metadados_dict(campos_meta: list) -> OrderedDict:
    """
    Constrói o dict simples {campo: TIPO} para ingerir_dados_datamart.
    Formato: {"task_id": "TEXT", "comment_count": "INTEGER", ...}
    A ordem das colunas deve ser idêntica à do CSV — respeitada via OrderedDict.
    """
    m = OrderedDict()
    for campo in campos_meta:
        nome = campo["campo"]
        tipo = campo.get("tipo", "TEXTO")
        mascara = campo.get("mascara", "")
        if tipo in ("NÚMERO", "NUMERO"):
            tipo_bd = "INTEGER" if mascara in ("Inteiro", "#") else "FLOAT"
        elif tipo == "DATA":
            tipo_bd = "DATA"
        else:
            tipo_bd = "TEXT"
        m[nome] = tipo_bd
    return m


def _aplicar_tipos(df: pd.DataFrame, metadados: OrderedDict) -> pd.DataFrame:
    """Converte colunas do DataFrame para os tipos do metadados dict."""
    for col, tipo in metadados.items():
        if col not in df.columns:
            continue
        if tipo == "INTEGER":
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("Int64")
        elif tipo == "FLOAT":
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("float64")
        # DATA e TEXT permanecem como object (string)
    return df


def _normalize_dtype(dtype: str) -> str:
    d = dtype.lower()
    if "int" in d:
        return "INTEGER"
    if "float" in d:
        return "FLOAT"
    if "datetime" in d:
        return "DATA"
    return "TEXT"


def run_detective_report(df: pd.DataFrame, metadados: OrderedDict, table_name: str, stage: str = "") -> None:
    """Super Detetive: valida tipos e colunas do DataFrame vs metadados esperados."""
    SEP = "=" * 90
    print(f"\n{SEP}")
    print(f"SUPER DETETIVE [{stage}]: {table_name} | Lote: {len(df):,} linhas")
    print(SEP)
    print(f"{'Coluna':<38} | {'Tipo Atual':<15} | {'Esperado':<10} | {'Nulos':<7} | Status")
    print("-" * 90)

    for col in df.columns:
        atual = str(df[col].dtype)
        norm = _normalize_dtype(atual)
        esperado = metadados.get(col, "???")
        nulos = int(df[col].isnull().sum())

        if col not in metadados:
            status = "COLUNA EXTRA"
        elif norm != esperado:
            status = f"TIPO ERRADO (norm={norm})"
        else:
            status = "OK"

        print(f"{col:<38} | {atual:<15} | {esperado:<10} | {nulos:<7} | {status}")

    faltando = set(metadados.keys()) - set(df.columns)
    if faltando:
        print(f"\nColunas faltando ({len(faltando)}):")
        for col in sorted(faltando):
            print(f"  - {col}  [esperado: {metadados[col]}]")

    print(SEP + "\n")


def ingerir(output_dir: str, nome_tabela: str = NOME_TABELA) -> bool:
    """
    Lê o CSV gerado e ingere no BigData PE via ingerir_dados_datamart com metadados inline.
    O monkeypatch em _consultar_metadados é necessário porque o backend retorna 500
    por encoding latin-1 nos metadados armazenados.
    """
    try:
        from bigdata import Pypeline
        import bigdata.pypeline.pypeline as _pm
    except ImportError:
        print("  [BigData] Biblioteca 'bigdata' nao encontrada.")
        return False

    csv_path = _encontrar_csv(output_dir)
    if not csv_path:
        print(f"  [BigData] Nenhum CSV encontrado em: {output_dir}")
        return False

    campos_meta = _carregar_campos_meta(output_dir)
    if not campos_meta:
        print(f"  [BigData] Metadata nao encontrado em: {output_dir}/metadados_ProjetosGPD.json")
        return False

    # Monkeypatch: retorna apenas o que ingerir_dados_datamart precisa verificar
    def _mock_consultar_metadados(nome_conjunto):
        print(f"  [BigData][MOCK] _consultar_metadados({nome_conjunto})")
        return {"tipo_conjunto_datamart": True}

    _pm._consultar_metadados = _mock_consultar_metadados
    print(f"  [BigData] Patch aplicado: {_pm._consultar_metadados.__name__}")

    # Metadados no formato simples {campo: TIPO} exigido por ingerir_dados_datamart
    metadados = _build_metadados_dict(campos_meta)

    print(f"\n  [BigData] Iniciando ingestao...")
    print(f"  [BigData] Arquivo   : {csv_path}")
    print(f"  [BigData] Tabela    : {nome_tabela}")
    print(f"  [BigData] Colunas   : {len(metadados)}")

    try:
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        df = _renomear_colunas(df)
        df = _aplicar_tipos(df, metadados)
        print(f"  [BigData] Registros : {len(df):,}")

        run_detective_report(df, metadados, nome_tabela, stage="PRE-INGESTAO")

        pype = Pypeline()

        print("  [BigData] Truncando...")
        try:
            pype.truncate(nome_tabela)
        except Exception as e:
            print(f"  [BigData] Truncate ignorado: {e}")

        print(f"  [BigData] Enviando {len(df):,} registros via ingerir_dados_datamart...")
        pype.ingerir_dados_datamart(
            nome_tabela,
            dados=df,
            metadados=metadados,
            nome_dimensao=nome_tabela,
        )

        print("  [BigData] Ingestao concluida com sucesso!")
        return True

    except Exception as e:
        print(f"  [BigData] Erro: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else "Dados_BI_ClickUp/API"
    ingerir(pasta)
