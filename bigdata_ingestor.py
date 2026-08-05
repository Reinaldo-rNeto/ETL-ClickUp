"""
bigdata_ingestor.py — Ingesta o CSV gerado pelo extrator no BigData PE via Pypeline.
"""

import os
import re
import glob
import unicodedata
import pandas as pd


NOME_TABELA = "projetosgpd"


def _normalizar_col(nome: str) -> str:
    """Converte nome de coluna CSV para snake_case ASCII — igual ao metadata_generator."""
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
    """Renomeia colunas para snake_case, desambiguando duplicatas."""
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
    """Localiza o CSV mais recente na pasta de saída."""
    padrao = os.path.join(output_dir, "*.csv")
    arquivos = sorted(glob.glob(padrao), key=os.path.getmtime, reverse=True)
    return arquivos[0] if arquivos else None


def ingerir(output_dir: str, nome_tabela: str = NOME_TABELA) -> bool:
    """
    Lê o CSV gerado, renomeia colunas para snake_case e ingere no BigData PE.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    try:
        from bigdata import Pypeline
    except ImportError:
        print("  [BigData] Biblioteca 'bigdata' não encontrada — ingestão ignorada.")
        return False

    csv_path = _encontrar_csv(output_dir)
    if not csv_path:
        print(f"  [BigData] Nenhum CSV encontrado em: {output_dir}")
        return False

    print(f"\n  [BigData] Iniciando ingestão...")
    print(f"  [BigData] Arquivo  : {csv_path}")
    print(f"  [BigData] Tabela   : {nome_tabela}")

    try:
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        df = _renomear_colunas(df)
        print(f"  [BigData] Registros : {len(df):,}")
        print(f"  [BigData] Colunas   : {len(df.columns)}")

        pype = Pypeline()

        print(f"  [BigData] Truncando tabela...")
        try:
            pype.truncate(nome_tabela)
        except Exception as e:
            print(f"  [BigData] Truncate ignorado: {e}")

        print(f"  [BigData] Enviando {len(df):,} registros...")
        pype.ingerir_dados(nome_tabela, df)

        print(f"  [BigData] Ingestão concluída com sucesso!")
        return True

    except Exception as e:
        print(f"  [BigData] Erro na ingestão: {e}")
        return False


if __name__ == "__main__":
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else "Dados_BI_ClickUp/API"
    ingerir(pasta)
