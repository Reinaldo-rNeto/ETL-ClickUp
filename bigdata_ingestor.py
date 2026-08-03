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
    Lê o CSV gerado e ingere no BigData PE via Pypeline.
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
        print(f"  [BigData] Registros: {len(df):,}")

        pype = Pypeline()

        print(f"  [BigData] Truncando tabela...")
        try:
            pype.truncate(nome_tabela)
        except Exception as e:
            print(f"  [BigData] Truncate ignorado (conjunto vazio ou primeira carga): {e}")

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
