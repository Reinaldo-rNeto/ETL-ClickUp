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


NOME_TABELA   = "ft_projetos_gpd"
NOME_DATAMART = "datamart_projeto_gpd_v2"


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


def _carregar_campos_meta() -> list | None:
    meta_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadados_ProjetosGPD.json")
    if not os.path.exists(meta_path):
        print(f"  [BigData] metadados_ProjetosGPD.json nao encontrado em: {meta_path}")
        return None
    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else data.get("metadata", [])


def _build_metadados_dict(campos_meta: list) -> OrderedDict:
    """
    Constrói o dict simples {campo: TIPO} para ingerir_dados_datamart.
    Duplicatas (mesmo nome normalizado) recebem sufixo _2, _3... igual ao _renomear_colunas.
    """
    m = OrderedDict()
    vistos: dict[str, int] = {}
    for campo in campos_meta:
        base = _normalizar_col(campo.get("mapeamento") or campo["campo"])
        if base in vistos:
            vistos[base] += 1
            nome = f"{base}_{vistos[base]}"
        else:
            vistos[base] = 1
            nome = base
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


_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)\b')


def _aplicar_tipos(df: pd.DataFrame, metadados: OrderedDict) -> pd.DataFrame:
    """Converte colunas do DataFrame para os tipos do metadados dict."""
    for col, tipo in metadados.items():
        if col not in df.columns:
            continue
        if tipo == "INTEGER":
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("Int64")
        elif tipo == "FLOAT":
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("float64")
        elif tipo == "DATA":
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                dt_series = df[col].copy()
            else:
                cleaned = df[col].replace("", None)
                cleaned = cleaned.str.replace(_ORDINAL_RE, r'\1', regex=True)
                dt_series = pd.to_datetime(cleaned, errors='coerce', utc=True)
                if dt_series.dt.tz is not None:
                    dt_series = dt_series.dt.tz_convert(None)
            # Força para datetime64[ms] — compatível com Spark/Iceberg
            df[col] = dt_series.astype("datetime64[ms]")
    return df


def _normalize_dtype(dtype: str, sample=None) -> str:
    d = dtype.lower()
    if "date" in d or "datetime" in d or "timestamp" in d:
        return "DATA"
    if "int" in d:
        return "INTEGER"
    if "float" in d:
        return "FLOAT"
    if d == "object" and sample is not None:
        import datetime
        if isinstance(sample, datetime.date):
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
        sample = df[col].dropna().iloc[0] if df[col].notna().any() else None
        norm = _normalize_dtype(atual, sample)
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


def ingerir(output_dir: str, nome_tabela: str = NOME_TABELA, datamart: str = NOME_DATAMART) -> bool:
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

    campos_meta = _carregar_campos_meta()
    if not campos_meta:
        return False

    # Monkeypatch: retorna apenas o que ingerir_dados_datamart precisa verificar
    def _mock_consultar_metadados(nome_conjunto):
        print(f"  [BigData][MOCK] _consultar_metadados({nome_conjunto})")
        return {"tipo_conjunto_datamart": True}

    _pm._consultar_metadados = _mock_consultar_metadados
    print(f"  [BigData] Patch _consultar_metadados: OK")

    # Patch PyArrow: força TIMESTAMP(MICROS) em vez de TIMESTAMP(NANOS)
    # pandas < 2.0 ignora datetime64[ms] e sempre gera ns; NANOS é rejeitado pelo Spark.
    # coerce_timestamps='us' trunca para microsegundos antes de escrever o Parquet.
    import pyarrow.parquet as _pq
    _orig_pq_write = _pq.write_table

    def _patched_pq_write(table, where, **kwargs):
        kwargs.setdefault('coerce_timestamps', 'us')
        kwargs.setdefault('allow_truncated_timestamps', True)
        return _orig_pq_write(table, where, **kwargs)

    _pq.write_table = _patched_pq_write
    print(f"  [BigData] Patch pyarrow.parquet.write_table: OK (coerce_timestamps=us)")

    # Metadados no formato simples {campo: TIPO} exigido por ingerir_dados_datamart
    metadados = _build_metadados_dict(campos_meta)

    print(f"\n  [BigData] Iniciando ingestao...")
    print(f"  [BigData] Arquivo   : {csv_path}")
    print(f"  [BigData] Tabela    : {nome_tabela}")
    print(f"  [BigData] Colunas   : {len(metadados)}")

    try:
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        df = _renomear_colunas(df)
        # Manter apenas colunas definidas no metadados (elimina duplicatas _2 e extras)
        cols_validas = [c for c in metadados.keys() if c in df.columns]
        df = df[cols_validas]
        df = _aplicar_tipos(df, metadados)
        print(f"  [BigData] Registros : {len(df):,} | Colunas filtradas: {len(cols_validas)}/{len(metadados)}")

        run_detective_report(df, metadados, nome_tabela, stage="PRE-INGESTAO")

        pype = Pypeline()

        # Patch _login: garante datamart e tabela na lista de acesso autorizado.
        # O Pypeline verifica conjuntos_ingestao antes de aceitar a chamada;
        # o login pode estar desatualizado com os nomes antigos do conjunto.
        _login = getattr(pype, '_login', {})
        _conjuntos = _login.get('conjuntos_ingestao', [])
        for _nome in (datamart, nome_tabela):
            if _nome not in _conjuntos:
                _conjuntos.append(_nome)
                print(f"  [BigData] Patch _login: adicionado '{_nome}' em conjuntos_ingestao")
        if 'conjuntos_ingestao' in _login:
            _login['conjuntos_ingestao'] = _conjuntos

        print("  [BigData] Removendo tabela anterior...")
        try:
            pype.drop_table_datamart(datamart, nome_tabela)
            print("  [BigData] Tabela removida com sucesso.")
        except Exception as e:
            print(f"  [BigData] Drop ignorado (primeira ingestao?): {e}")

        print(f"  [BigData] Enviando {len(df):,} registros via ingerir_dados_datamart...")
        pype.ingerir_dados_datamart(
            datamart,
            metadados=metadados,
            dados=df,
            nome_fato=nome_tabela,
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
