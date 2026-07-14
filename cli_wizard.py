#!/usr/bin/env python3
"""
cli_wizard.py — Assistente interativo para o Extrator ClickUp — ATI Pernambuco
Uso: python cli_wizard.py
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta

# ── ANSI Colors ────────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def _c(t, color): return f"{color}{t}{RESET}"
def bold(t):      return f"{BOLD}{t}{RESET}"
def dim(t):       return f"{DIM}{t}{RESET}"

_WIN = sys.platform == "win32"
CHECK = "[OK]"  if _WIN else "✓"
CROSS = "[X]"   if _WIN else "✗"
ARROW = "->"    if _WIN else "→"

# ── Helpers de entrada ─────────────────────────────────────────────────────────

def _input(prompt):
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperacao cancelada.")
        sys.exit(0)

def ask(prompt, default="", validator=None):
    hint = f" [{dim(default)}]" if default else ""
    while True:
        val = _input(f"  {prompt}{hint}: ")
        if not val and default is not None:
            val = default
        if validator:
            ok, msg = validator(val)
            if not ok:
                print(f"  {_c(CROSS, RED)} {msg}")
                continue
        return val

def yes(prompt, default=True):
    hint = "S/n" if default else "s/N"
    val = _input(f"  {prompt} [{hint}]: ").lower()
    return val in ("s", "sim", "y", "yes") if val else default

def menu(title, options, default=1):
    """Menu numerado. options = [(label, desc), ...]"""
    print(f"\n  {bold(title)}")
    for i, (lbl, desc) in enumerate(options, 1):
        marker = _c(f"  {i}.", CYAN)
        print(f"{marker} {bold(lbl)}")
        if desc:
            print(f"       {dim(desc)}")
    while True:
        val = _input(f"\n  Escolha [{dim(str(default))}]: ")
        val = val or str(default)
        if val.isdigit() and 1 <= int(val) <= len(options):
            return int(val) - 1
        print(f"  {_c(CROSS, RED)} Digite um numero de 1 a {len(options)}")

def multi(title, items, default_all=False):
    """Selecao multipla. Retorna lista de indices."""
    print(f"\n  {bold(title)}")
    for i, name in enumerate(items, 1):
        print(f"  {_c(str(i) + '.', CYAN)} {name}")
    print(f"  {_c('0.', CYAN)} {bold('Todos')}")
    hint = "0" if default_all else "ex: 1,3"
    while True:
        val = _input(f"\n  Selecione [{dim(hint)}]: ")
        val = val or ("0" if default_all else "")
        if not val:
            continue
        if val == "0":
            return list(range(len(items)))
        parts = [p.strip() for p in val.split(",")]
        result, ok = [], True
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= len(items):
                idx = int(p) - 1
                if idx not in result:
                    result.append(idx)
            else:
                print(f"  {_c(CROSS, RED)} '{p}' invalido. Use numeros de 1 a {len(items)} separados por virgula.")
                ok = False
                break
        if ok and result:
            return result

def sep():
    print(f"\n  {dim('─' * 60)}")

def header(step, total, title):
    print(f"\n{_c('━' * 64, CYAN)}")
    print(f"  {dim(f'Passo {step} de {total}')}   {bold(title)}")
    print(_c('━' * 64, CYAN))

def ok(msg):  print(f"  {_c(CHECK, GREEN)} {msg}")
def err(msg): print(f"  {_c(CROSS, RED)} {msg}")
def info(msg): print(f"  {_c(ARROW, BLUE)} {msg}")

# ── Banner ─────────────────────────────────────────────────────────────────────

def banner():
    print(_c("━" * 64, CYAN))
    print(_c("  Extrator ClickUp — ATI Pernambuco", BOLD + CYAN))
    print(_c("  Assistente de configuracao e extracao", DIM))
    print(_c("━" * 64, CYAN))
    print()

# ── Passo 1: Credenciais ───────────────────────────────────────────────────────

def passo_credenciais():
    header(1, 6, "Credenciais")
    print()

    # Carrega .env se existir
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            info(f".env carregado de: {env_path}")
        except ImportError:
            pass

    token = os.environ.get("CLICKUP_API_TOKEN", "").strip("\"'")
    if not token:
        print(f"  {_c('CLICKUP_API_TOKEN', YELLOW)} nao encontrado no ambiente.\n")
        token = ask("Informe o API Token do ClickUp", validator=lambda v: (bool(v), "Token nao pode ser vazio"))
        os.environ["CLICKUP_API_TOKEN"] = token
    else:
        ok(f"CLICKUP_API_TOKEN carregado  ({token[:12]}...)")

    # Testa conexao
    try:
        from clickup_client import ClickUpClient
        client = ClickUpClient()
        teams = client.get_teams()
        if not teams:
            err("Token invalido ou sem acesso a nenhum workspace.")
            sys.exit(1)
        ok(f"Conectado. {len(teams)} workspace(s) encontrado(s).")
        return client, teams
    except Exception as e:
        err(f"Falha na conexao: {e}")
        sys.exit(1)

# ── Passo 2: Modo de extraçao ──────────────────────────────────────────────────

MODOS = [
    ("Consolidado via API",
     "Extrai tarefas das views 'Resumo BI' e gera CSV + XLSX unificado  [recomendado para pipelines]"),
    ("Exportacao nativa  (Playwright)",
     "Baixa XLSX+CSV direto do ClickUp via navegador  [requer email/senha]"),
    ("Dados e planilha",
     "Extrai todas as tarefas via API e gera JSON + XLSX"),
    ("Relatorio completo",
     "PDF por tarefa + JSON + anexos + XLSX  [mais lento]"),
]

MODO_VALS = ["apenas_csv_api", "apenas_csv", "csv_json", "completo"]

def passo_modo():
    header(2, 6, "Tipo de extracao")
    idx = menu("Qual tipo de extracao deseja realizar?", MODOS, default=1)
    modo = MODO_VALS[idx]
    ok(f"Modo selecionado: {MODOS[idx][0]}")

    pw_email, pw_pass = "", ""
    if modo == "apenas_csv":
        sep()
        print(f"\n  {bold('Credenciais para login no ClickUp (Playwright)')}")
        pw_email = os.environ.get("CLICKUP_EMAIL", "").strip("\"'")
        pw_pass  = os.environ.get("CLICKUP_PASSWORD", "").strip("\"'")
        if pw_email and pw_pass:
            ok(f"CLICKUP_EMAIL: {pw_email}")
            ok("CLICKUP_PASSWORD: ****")
        else:
            pw_email = ask("Email do ClickUp", default=pw_email or "")
            pw_pass  = ask("Senha do ClickUp",  default="")
            os.environ["CLICKUP_EMAIL"]    = pw_email
            os.environ["CLICKUP_PASSWORD"] = pw_pass

    return modo, pw_email, pw_pass

# ── Passo 3: Espacos ───────────────────────────────────────────────────────────

def passo_espacos(client, teams):
    header(3, 6, "Espacos do ClickUp")
    print()
    info("Consultando espacos disponiveis...")

    all_spaces = []
    for team in teams:
        spaces = client.get_spaces(team["id"])
        all_spaces.extend(spaces)

    if not all_spaces:
        err("Nenhum espaco encontrado.")
        sys.exit(1)

    names = [s["name"] for s in all_spaces]
    indices = multi("Selecione os espacos para extrair:", names, default_all=False)
    selected = [all_spaces[i] for i in indices]

    sep()
    ok(f"{len(selected)} espaco(s) selecionado(s):")
    for s in selected:
        info(s["name"])

    return selected

# ── Passo 4: Saida ─────────────────────────────────────────────────────────────

def passo_saida(modo):
    header(4, 6, "Pasta de saida")
    print()

    base = os.path.dirname(os.path.abspath(__file__))
    if modo == "apenas_csv_api":
        default_dir = os.path.join(base, "Dados_BI_ClickUp", "API")
    elif modo == "apenas_csv":
        default_dir = os.path.join(base, "Dados_BI_ClickUp", "Playwright")
    else:
        default_dir = os.path.join(base, "Dados_Extraidos_ClickUp")

    output_dir = ask("Pasta de saida", default=default_dir)
    os.makedirs(output_dir, exist_ok=True)
    ok(f"Pasta: {output_dir}")
    return output_dir

# ── Passo 5: Filtros (opcional) ────────────────────────────────────────────────

def passo_filtros():
    header(5, 6, "Filtros  (opcional)")
    print()

    usar = yes("Deseja aplicar filtros?", default=False)
    if not usar:
        info("Sem filtros — extraindo tudo.")
        return "", "Todas", ""

    sep()
    sprint = ask("Filtro por sprint/lista (deixe em branco para nenhum)", default="")
    status = ask("Filtro por status", default="Todas")
    date_gt = ask("Extrair apenas tarefas atualizadas apos (DD/MM/AAAA, ou em branco)", default="")

    return sprint, status, date_gt

# ── Passo 6: Agendamento ───────────────────────────────────────────────────────

_DIAS_NOMES = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
_DIAS_KEYS  = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]

def passo_agendamento(modo, space_ids, output_dir, sprint, status):
    header(6, 6, "Agendamento")
    print()

    agendar = yes("Deseja configurar agendamento automatico?", default=False)
    if not agendar:
        info("Sem agendamento configurado.")
        return None

    sep()
    print(f"\n  {bold('Dias da semana')}")
    print(f"  {dim('Digite os numeros dos dias separados por virgula (ex: 1,2,3,4,5)')}")
    for i, (k, n) in enumerate(zip(_DIAS_KEYS, _DIAS_NOMES), 1):
        print(f"  {_c(str(i) + '.', CYAN)} {n}")

    while True:
        val = _input(f"\n  Dias [{dim('1,2,3,4,5')}]: ") or "1,2,3,4,5"
        parts = [p.strip() for p in val.split(",")]
        dias = []
        ok_flag = True
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= 7:
                dias.append(_DIAS_KEYS[int(p) - 1])
            else:
                print(f"  {_c(CROSS, RED)} '{p}' invalido.")
                ok_flag = False
                break
        if ok_flag and dias:
            break

    def _val_hora(v):
        try:
            datetime.strptime(v, "%H:%M")
            return True, ""
        except ValueError:
            return False, "Formato invalido. Use HH:MM (ex: 08:00)"

    h_ini = ask("Horario de inicio", default="08:00", validator=_val_hora)
    h_fim = ask("Horario de fim",    default="19:00", validator=_val_hora)

    def _val_int(v):
        return (v.isdigit() and int(v) >= 0, "Informe um numero inteiro >= 0")

    iv_h = ask("Repetir a cada X horas",   default="1", validator=_val_int)
    iv_m = ask("Repetir a cada X minutos", default="0", validator=_val_int)

    cfg = {
        "ativo": True,
        "dias_semana": dias,
        "hora_inicio": h_ini,
        "hora_fim": h_fim,
        "iv_horas": int(iv_h),
        "iv_minutos": int(iv_m),
        "output_mode": modo,
        "space_ids": space_ids,
        "output_dir": output_dir,
        "ultima_execucao": "",
    }

    # Salva agendamento.json
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agendamento.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    sep()
    ok(f"Configuracao salva em: {cfg_path}")
    nomes_dias = " ".join(_DIAS_NOMES[_DIAS_KEYS.index(d)] for d in dias)
    info(f"Dias: {nomes_dias}")
    info(f"Janela: {h_ini} ate {h_fim}")
    info(f"Intervalo: {iv_h}h {iv_m}min")

    return cfg

# ── Confirmacao e execucao ─────────────────────────────────────────────────────

def confirmacao_e_run(modo, selected_spaces, output_dir, sprint, status, date_gt, sch_cfg):
    space_ids = ",".join(s["id"] for s in selected_spaces)
    modo_label = dict(zip(MODO_VALS, [m[0] for m in MODOS]))[modo]

    print(f"\n{_c('━' * 64, GREEN)}")
    print(f"  {bold('Resumo da configuracao')}")
    print(_c('━' * 64, GREEN))
    info(f"Modo          : {bold(modo_label)}")
    info(f"Espacos       : {', '.join(s['name'] for s in selected_spaces)}")
    info(f"Pasta de saida: {output_dir}")
    if sprint:  info(f"Sprint        : {sprint}")
    if status != "Todas": info(f"Status        : {status}")
    if date_gt: info(f"Data min.     : {date_gt}")
    if sch_cfg:
        nomes = " ".join(_DIAS_NOMES[_DIAS_KEYS.index(d)] for d in sch_cfg["dias_semana"])
        info(f"Agendamento   : {nomes}  {sch_cfg['hora_inicio']}–{sch_cfg['hora_fim']}  a cada {sch_cfg['iv_horas']}h {sch_cfg['iv_minutos']}min")

    # Comando equivalente
    cmd_parts = [
        sys.executable, "main.py",
        "--output_mode", modo,
        "--space_ids",   space_ids,
        "--output_dir",  output_dir,
    ]
    if sprint:  cmd_parts += ["--sprint_filter", sprint]
    if status != "Todas": cmd_parts += ["--status_filter", status]
    if date_gt: cmd_parts += ["--date_gt", date_gt]

    sep()
    print(f"\n  {bold('Comando equivalente (para pipeline/cron):')}")
    print(f"  {_c(' '.join(cmd_parts), YELLOW)}\n")

    rodar = yes("Iniciar extracao agora?", default=True)
    if not rodar:
        info("Nenhuma extracao iniciada. Use o comando acima para rodar manualmente.")
        return

    print(f"\n{_c('━' * 64, CYAN)}")
    print(f"  {bold('Iniciando extracao...')}")
    print(_c('━' * 64, CYAN) + "\n")

    # Executa main.py como subprocesso para capturar saida em tempo real
    env = os.environ.copy()
    result = subprocess.run(cmd_parts, env=env)

    print(f"\n{_c('━' * 64, GREEN if result.returncode == 0 else RED)}")
    if result.returncode == 0:
        ok(f"Extracao concluida com sucesso!")
        info(f"Arquivos salvos em: {output_dir}")
    else:
        err(f"Extracao encerrada com codigo {result.returncode}")
    print(_c('━' * 64, GREEN if result.returncode == 0 else RED))

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    banner()

    # 1. Credenciais
    client, teams = passo_credenciais()

    # 2. Modo
    modo, pw_email, pw_pass = passo_modo()

    # 3. Espacos
    selected = passo_espacos(client, teams)
    space_ids = ",".join(s["id"] for s in selected)

    # 4. Saida
    output_dir = passo_saida(modo)

    # 5. Filtros
    sprint, status, date_gt = passo_filtros()

    # 6. Agendamento
    sch_cfg = passo_agendamento(modo, space_ids, output_dir, sprint, status)

    # Confirmacao + execucao
    confirmacao_e_run(modo, selected, output_dir, sprint, status, date_gt, sch_cfg)


if __name__ == "__main__":
    main()
