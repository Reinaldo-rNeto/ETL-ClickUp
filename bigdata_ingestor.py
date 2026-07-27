"""
bigdata_ingestor.py — Ingesta o CSV gerado pelo extrator no BigData PE via Pypeline.
"""

import os
import glob
import pandas as pd


NOME_TABELA = "ProjetosGPD"


def _encontrar_csv(output_dir: str) -> str | None:
    """Localiza o CSV mais recente na pasta de saída."""
    padrao = os.path.join(output_dir, "*.csv")
    arquivos = sorted(glob.glob(padrao), key=os.path.getmtime, reverse=True)
    return arquivos[0] if arquivos else None


def ingerir(output_dir: str, nome_tabela: str = NOME_TABELA) -> bool:
    """
    Lê o CSV gerado, prepara e ingere no BigData PE.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    try:
        from bigdata import Pypeline, prepare_dataframe_for_ingestion
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
        print(f"  [BigData] Registros: {len(df):,}")

        pype = Pypeline()
        pype._login

        df_final = prepare_dataframe_for_ingestion(df, nome_tabela)

        print(f"  [BigData] Truncando tabela...")
        pype.truncate(nome_tabela)

        print(f"  [BigData] Enviando {len(df_final):,} registros...")
        pype.ingerir_dados(nome_tabela, df_final)

        print(f"  [BigData] Ingestão concluída com sucesso!")
        return True

    except Exception as e:
        print(f"  [BigData] Erro na ingestão: {e}")
        return False
