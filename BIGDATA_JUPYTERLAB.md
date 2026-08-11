# BigData PE + JupyterLab — Aprendizados e Referência Técnica

Documento gerado em 2026-08-07. Consolida tudo que foi aprendido durante a integração do Extrator ClickUp com o BigData PE.

---

## 1. Ambiente

### JupyterLab (bigdata.pe.gov.br)

| Item | Valor |
|---|---|
| Python | `/opt/conda/bin/python` |
| Versão pandas | < 2.0 (comportamento diferente do pandas moderno) |
| Path do projeto | `/home/jovyan/automacao-clickup/` |
| Biblioteca BigData | `from bigdata import Pypeline` |

### GitLab

| Item | Valor |
|---|---|
| Remote | `https://gitlab.pe.gov.br/dic-gda/experimentalgda/automacao-clickup.git` |
| Branch | `main` |

---

## 2. Comandos essenciais no JupyterLab

### Localizar o projeto (se o path mudar)
```bash
find / -name "main.py" -path "*/automacao-clickup/*" 2>/dev/null | head -5
```

### Atualizar código do GitLab (preservando .env local)
```bash
cd ~/automacao-clickup
git stash
git pull
git checkout stash -- .env
git stash drop
```
> **IMPORTANTE:** Sempre usar este fluxo. Um `git pull` direto sobrescreve o `.env` que tem credenciais locais do JupyterLab.

### Rodar extração + ingestão manualmente
```bash
cd ~/automacao-clickup && /opt/conda/bin/python main.py --output_mode apenas_csv_api
```

---

## 3. Fluxo de execução

```
main.py --output_mode apenas_csv_api
  │
  ├─ build_bi_plan()
  │    └─ Varre todos os espaços do ClickUp buscando views "Resumo BI"
  │       (PORTFÓLIO PROJ ESTRATÉGICOS, PORTFÓLIO DE ARP, SUSPENSOS/BACKLOG, CONCLUÍDOS)
  │
  ├─ process_resumo_bi()  ← para cada view encontrada
  │    └─ Extrai tarefas via API → ExcelBIWriter.append_task()
  │
  ├─ ExcelBIWriter.finalize_xlsx()
  │    └─ Gera: Dados_BI_ClickUp/API/Relatorio_BI_Geral.csv + .xlsx
  │
  └─ bigdata_ingestor.ingerir("Dados_BI_ClickUp/API")
       └─ Lê CSV → aplica tipos → ingesta no datamart_projetos_gpd
```

---

## 4. BigData PE — Pypeline

### Chamada correta do ingerir_dados_datamart

```python
pype.ingerir_dados_datamart(
    datamart,              # 1º arg = nome do datamart (não da tabela!)
    metadados=metadados,   # dict {campo: TIPO} — vem ANTES de dados=
    dados=df,
    nome_fato=nome_tabela, # usar nome_fato (não nome_dimensao)
)
```

### Constantes do projeto

```python
NOME_TABELA   = "ft_projetos_gpd"        # prefixo ft_ = fato
NOME_DATAMART = "datamart_projetos_gpd"
```

### Tipos aceitos no metadados dict

| Tipo | Uso |
|---|---|
| `"TEXT"` | Strings, IDs, textos livres |
| `"INTEGER"` | Números inteiros (`Int64`) |
| `"FLOAT"` | Números decimais (`float64`) |
| `"DATA"` | Datas/timestamps |

### Drop antes de ingerir

```python
# Substituiu truncate() que não funcionava
try:
    pype.drop_table_datamart(datamart, nome_tabela)
except Exception as e:
    print(f"Drop ignorado (primeira ingestao?): {e}")
```

---

## 5. Os 3 Monkeypatches Obrigatórios

Todos aplicados dentro de `bigdata_ingestor.ingerir()`, antes de instanciar `Pypeline()`.

### Patch 1 — `_consultar_metadados` (bypass HTTP 500)

**Problema:** Backend do BigData PE retorna HTTP 500 ao consultar metadados por erro de encoding latin-1 nos dados armazenados.

```python
import bigdata.pypeline.pypeline as _pm

def _mock_consultar_metadados(nome_conjunto):
    return {"tipo_conjunto_datamart": True}

_pm._consultar_metadados = _mock_consultar_metadados
```

### Patch 2 — PyArrow `write_table` (TIMESTAMP NANOS → MICROS)

**Problema:** pandas < 2.0 converte `datetime64[ms]` silenciosamente para `datetime64[ns]`. PyArrow escreve como `TIMESTAMP(NANOS, false)` que o Spark desta versão rejeita com:
```
Illegal Parquet type: INT64 (TIMESTAMP(NANOS,false))
```

```python
import pyarrow.parquet as _pq
_orig_pq_write = _pq.write_table

def _patched_pq_write(table, where, **kwargs):
    kwargs.setdefault('coerce_timestamps', 'us')
    kwargs.setdefault('allow_truncated_timestamps', True)
    return _orig_pq_write(table, where, **kwargs)

_pq.write_table = _patched_pq_write
```

### Patch 3 — `_login['conjuntos_ingestao']` (PermissionError)

**Problema:** `Pypeline()` verifica se o datamart/tabela estão na lista `conjuntos_ingestao` do `_login`. O login pode conter nomes antigos (ex: `"projetosgpd"`) e rejeitar os nomes atuais.

```python
pype = Pypeline()

_login = getattr(pype, '_login', {})
_conjuntos = _login.get('conjuntos_ingestao', [])
for _nome in (datamart, nome_tabela):
    if _nome not in _conjuntos:
        _conjuntos.append(_nome)
        print(f"Patch _login: adicionado '{_nome}'")
if 'conjuntos_ingestao' in _login:
    _login['conjuntos_ingestao'] = _conjuntos
```

---

## 6. Datas — Problema e Solução

### Formato ClickUp
ClickUp retorna datas no formato: `"Wednesday, February 11th 2026"` (com sufixos ordinais).

### Solução

```python
import re
_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)\b')

cleaned = df[col].replace("", None)
cleaned = cleaned.str.replace(_ORDINAL_RE, r'\1', regex=True)
dt_series = pd.to_datetime(cleaned, errors='coerce', utc=True)
if dt_series.dt.tz is not None:
    dt_series = dt_series.dt.tz_convert(None)
df[col] = dt_series.astype("datetime64[ms]")  # ms, não ns!
```

> `datetime64[ms]` é a escolha correta. pandas < 2.0 converte para ns internamente, mas o Patch 2 resolve isso no PyArrow.

---

## 7. Super Detetive — Diagnóstico pré-ingestão

Função `run_detective_report()` em `bigdata_ingestor.py`. Mostra coluna por coluna o tipo atual vs esperado antes de enviar ao BigData PE.

```
SUPER DETETIVE [PRE-INGESTAO]: ft_projetos_gpd | Lote: 117 linhas
Coluna                                 | Tipo Atual      | Esperado   | Nulos   | Status
-----------------------------------------------------------------------------------------------
task_id                                | object          | TEXT       | 0       | OK
due_date                               | datetime64[ms]  | DATA       | 45      | OK
comment_count                          | Int64           | INTEGER    | 0       | OK
```

---

## 8. Rate Limit do ClickUp API

### Problema
Com apenas 3 tentativas e 2s de espera, espaços com muitas pastas (ex: PORTFÓLIO DE ARP) esgotam as tentativas durante o scan de views e a "Resumo BI" não é encontrada — sem nenhum erro visível.

### Solução atual (`clickup_client.py`)

```python
retries = 15
for attempt in range(retries):
    if response.status_code == 429:
        wait = min(5 * (attempt + 1), 60)  # 5s, 10s, 15s... max 60s
        print(f"Rate limit atingido. Aguardando {wait}s...")
        time.sleep(wait)
        continue
```

### Overrides manuais de views

Para espaços onde a API não retorna a view (ou como fallback):

```python
# main.py
_MANUAL_VIEW_OVERRIDES: dict[str, str] = {
    "90131678068": "4-90131678068-23",  # PROJETOS CONCLUÍDOS/CANCELADOS
}
```

---

## 9. Playwright REMOVIDO

O modo Playwright (`apenas_csv`) foi completamente removido em 2026-08-07.

**Por quê:** JupyterLab não tem navegador. O modo ficava preso em `Aguardando /tmp/proxy.lock...` e depois falhava silenciosamente sem gerar CSV.

**Modos disponíveis atualmente:**
- `apenas_csv_api` — **padrão para BigData PE** (extrai via API, ingesta automaticamente)
- `csv_json` — extrai todas as tarefas via API, gera JSON + XLSX
- `completo` — PDF por tarefa + JSON + anexos + XLSX

---

## 10. Estrutura de arquivos gerados

```
Dados_BI_ClickUp/
└─ API/
   ├─ Relatorio_BI_Geral.csv          ← ingerido no BigData PE
   ├─ Relatorio_BI_Geral_Geral.xlsx
   └─ metadados_ProjetosGPD.json
```

---

## 11. Erros conhecidos e soluções

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 500 _consultar_metadados` | Encoding latin-1 no backend | Patch 1 |
| `TIMESTAMP(NANOS,false) illegal` | pandas < 2.0 + PyArrow | Patch 2 |
| `PermissionError: sem acesso ao conjunto` | `_login` desatualizado | Patch 3 |
| `Cannot safely cast 'due_date': string to date` | Sufixos ordinais nas datas | `_ORDINAL_RE` |
| `Nenhum CSV encontrado` | Rodando `bigdata_ingestor.py` direto sem extração | Rodar `main.py --output_mode apenas_csv_api` |
| View "Resumo BI" não encontrada | Rate limit esgota 3 tentativas | Backoff progressivo (15 tentativas) |
| `error: Your local changes would be overwritten` | .env local diverge do remoto | `git stash` antes do `git pull` |
