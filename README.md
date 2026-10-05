# ETL ClickUp → BigData PE

Pipeline de extração, transformação e carga de dados do **ClickUp** para o **BigData PE** (data lakehouse da ATI Pernambuco).

---

## Visão Geral

```
ClickUp API
    │
    ▼
[ Extract ]  clickup_client.py  — consulta tasks, custom fields, time-in-status
    │
    ▼
[ Transform ] excel_writer.py   — normaliza colunas, converte tipos, strip de emojis,
              bigdata_ingestor.py  mapeamento via metadados JSON, deduplicação
    │
    ▼
[ Load ]     bigdata_ingestor.py — ingere no BigData PE via Pypeline (Parquet/Spark)
```

**Destino:** `datamart_projeto_gpd_v2`
- `ft_projetos_gpd` — 130 colunas com dados de todos os projetos GPD
- `ft_atualizacao_gpd` — data/hora e total de registros da última carga

---

## Estrutura de Arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `main.py` | Ponto de entrada; orquestra extração e carga |
| `clickup_client.py` | Cliente da API REST do ClickUp (tasks, views, custom fields) |
| `excel_writer.py` | Transformação e geração do CSV/XLSX |
| `bigdata_ingestor.py` | Carga no BigData PE via Pypeline |
| `data_writer.py` | Geração de arquivos locais (JSON, PDF, hierarquia de pastas) |
| `attachment_downloader.py` | Download de anexos das tarefas |
| `metadados_ProjetosGPD.json` | Mapeamento campo ClickUp → coluna BigData PE |
| `mapeamento_pastas.json` | Associação de pastas do ClickUp com pessoas e projetos na planilha local |

---

## Pré-requisitos

- Python 3.11+
- Dependências: `requests`, `python-dotenv`, `pandas`, `openpyxl`, `pyarrow`
- Acesso à API do ClickUp (token pessoal)
- Ambiente BigData PE com biblioteca `bigdata` instalada (JupyterLab)

---

## Configuração

Crie um arquivo `.env` na raiz do projeto (nunca commitar):

```env
CLICKUP_API_TOKEN=pk_...
CLICKUP_EMAIL=...@...
CLICKUP_PASSWORD=...
TEAM_ID=...
```

---

## Modos de Execução

| Modo | Descrição |
|------|-----------|
| `apenas_csv_api` | Extrai views "Resumo BI" e gera CSV + XLSX. **Padrão para BigData PE.** |
| `csv_json` | Extrai todas as tarefas e gera JSON + XLSX |
| `completo` | PDF por tarefa + JSON + download de anexos + XLSX |

---

## Execução

### Local (Windows)

```bash
python main.py --output_mode apenas_csv_api
```

Saída gerada em: `Dados_BI_ClickUp/API/Relatorio_BI_Geral.xlsx`

### BigData PE (JupyterLab)

```bash
cd ~/shared/ati/etl_temporaria
git pull origin main
PYTHONUNBUFFERED=1 /opt/conda/bin/python -u main.py --output_mode apenas_csv_api 2>&1 | tee /tmp/extrator_log.txt
```

### Argumentos disponíveis

```
--output_mode    Modo de extração (padrão: apenas_csv_api)
--space_ids      IDs de spaces ClickUp separados por vírgula (padrão: todos)
--output_dir     Pasta de saída (padrão: Dados_BI_ClickUp/API)
--status_filter  Todas | Somente Abertas | Somente Fechadas (padrão: Todas)
--date_gt        Filtrar tarefas atualizadas após esta data (YYYY-MM-DD)
--preview_only   Apenas exibe o plano de extração sem executar
```

---

## Views Extraídas (modo apenas_csv_api)

As views são fixas e apontam para os espaços GPD no ClickUp:

| Espaço | View |
|--------|------|
| PORTFÓLIO DE PROJ ESTRATÉGICOS | Resumo BI |
| PORTFÓLIO DE ARP | Resumo BI |
| PROJETOS CONCLUÍDOS/CANCELADOS | Resumo BI |
| PROJETOS SUSPENSOS/BACKLOG | Resumo BI |

---

## Metadados e Mapeamento de Colunas

O relatório inclui a coluna `area_consumidora`, preenchida por padrão com `GPD`. Para uma pasta específica do ClickUp, é possível configurar outra área, pessoa responsável e projeto associado em `mapeamento_pastas.json`. Exemplo:

```json
{
  "area_padrao": "GPD",
  "pastas": [
    { "pasta_clickup": "Pasta Ironita A", "area_consumidora": "GRGD",
      "pessoa": "Nome da pessoa", "projeto": "Nome do projeto" }
  ],
  "espacos": [
    { "espaco_clickup": "Projeto Ironita B", "area_consumidora": "GRGD",
      "pessoa": "Nome da pessoa", "projeto": "Nome do projeto" }
  ]
}
```

As chaves `pasta_clickup` e `espaco_clickup` são comparadas sem diferenciar maiúsculas/minúsculas. A regra de pasta tem prioridade sobre a regra de espaço. Os modos `csv_json` e `completo` também preenchem `Pasta de Arquivos` com o caminho local de cada tarefa. No modo `apenas_csv_api`, esse caminho fica vazio porque não são criadas pastas locais por tarefa. As associações de pessoa/projeto saem nos CSV/XLSX locais. `area_consumidora` também está em `metadados_ProjetosGPD.json` para seguir na carga ao BigData; a tabela de destino precisa aceitar essa coluna. Projetos sem view podem ser anotados em `projetos_pendentes`; eles não entram na extração até que a view esteja disponível.

### Metadados do BigData PE

O arquivo `metadados_ProjetosGPD.json` define o mapeamento entre campos do ClickUp e colunas do BigData PE:

```json
{
  "campo": "Nome do campo no ClickUp",
  "mapeamento": "nome_coluna_bigdata",
  "tipo": "TEXTO | NÚMERO | DATA",
  "mascara": "Inteiro | # | vazio",
  "categoria": "DADO COMUM | CUSTOM FIELD"
}
```

Tipos mapeados para o BigData PE:

| Tipo JSON | Tipo BigData PE |
|-----------|----------------|
| `TEXTO` | TEXT |
| `NÚMERO` (Inteiro / #) | INTEGER |
| `NÚMERO` (outros) | FLOAT |
| `DATA` | TIMESTAMP |

---

## Ingestão no BigData PE

O `bigdata_ingestor.py` aplica três monkeypatches necessários para compatibilidade:

1. **`_consultar_metadados`** — contorna erro HTTP 500 do backend (encoding latin-1)
2. **PyArrow `write_table`** — força `TIMESTAMP(MICROS)` em vez de NANOS (rejeitado pelo Spark)
3. **`_login.conjuntos_ingestao`** — garante que datamart e tabela estejam na lista de acesso

---

## Agendamento no BigData PE

O agendador nativo do BigData PE aponta para `main.py` com `--output_mode apenas_csv_api`. A extração é disparada automaticamente conforme configuração da plataforma.

---

## Repositórios

| Ambiente | URL |
|----------|-----|
| GitLab (ATI) | `https://gitlab.pe.gov.br/dic-gda/experimentalgda/automacao-clickup.git` |
| GitHub | `https://github.com/Reinaldo-rNeto/ETL-ClickUp.git` |
