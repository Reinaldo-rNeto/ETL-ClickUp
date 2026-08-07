import os
import sys
import time
import argparse
import datetime
from clickup_client import ClickUpClient
from data_writer import DataWriter
from attachment_downloader import AttachmentDownloader
from excel_writer import ExcelBIWriter


def _fmt_elapsed(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


def _sprint_matches(list_name, sprint_filter):
    """Retorna True se a lista bate com o filtro de sprint (ou se não há filtro)."""
    return not sprint_filter or sprint_filter.lower() in list_name.lower()


def _pilot_done(is_pilot, success, client, writer, output_mode):
    """Encerra o modo piloto se a primeira lista foi processada com sucesso."""
    if is_pilot and success:
        post_process_empty_shells(client, writer, output_mode)
        print("[PILOTO FINALIZADO]")
        return True
    return False


# Views fixas do Resumo BI — IDs retirados diretamente das URLs do ClickUp
# Formato: (space_name, view_name, view_id)
_BI_VIEWS = [
    ("PORTFÓLIO DE PROJ ESTRATÉGICOS", "Resumo BI", "8cktan6-259693"),
    ("PORTFÓLIO DE ARP",               "Resumo BI", "4-90131683703-23"),
    ("PROJETOS CONCLUÍDOS/CANCELADOS", "Resumo BI", "4-90131678068-23"),
    ("PROJETOS SUSPENSOS/BACKLOG",     "Resumo BI", "8cktan6-259233"),
]


def _is_resumo_bi_view(view_name: str) -> bool:
    return view_name.strip().lower() in _RESUMO_BI_NAMES


def _find_bi_view_in_views(views):
    """Retorna a primeira view cujo nome bate com Resumo BI, ou None."""
    for v in views:
        if _is_resumo_bi_view(v.get("name", "")):
            return v
    return None


def build_bi_plan(client, args):
    """
    Descobre automaticamente todas as views 'Resumo BI' no workspace.
    Busca em todos os níveis: espaço → pastas → listas.
    Nenhuma configuração manual necessária — novas inclusões são detectadas automaticamente.
    """
    bi_plan = []
    seen_view_ids = set()
    teams = client.get_teams()
    if not teams:
        return bi_plan

    for team in teams:
        team_id = team["id"]
        if args.workspace and args.workspace != "Todos" and args.workspace != team_id:
            continue

        spaces = client.get_spaces(team_id)
        selected_ids = set(filter(None, args.space_ids.split(","))) if args.space_ids else set()

        for space in spaces:
            if selected_ids and space["id"] not in selected_ids:
                continue
            space_id   = space["id"]
            space_name = space["name"]
            print(f"    [Space] {space_name}")

            def _add_view(v, label=""):
                if v["id"] not in seen_view_ids:
                    seen_view_ids.add(v["id"])
                    bi_plan.append((space_name, v["name"], v["id"], space_id))
                    where = f" ({label})" if label else ""
                    print(f"      → '{v['name']}'{where} (id: {v['id']})")

            # 0. Override manual — para views não retornadas pela API
            override_vid = _MANUAL_VIEW_OVERRIDES.get(space_id)
            if override_vid:
                _add_view({"id": override_vid, "name": "Resumo BI"}, "override manual")
                continue  # já encontrou, não precisa buscar mais fundo

            # 1. Nível espaço — se encontrar aqui, não precisa varrer pastas/listas
            sv = _find_bi_view_in_views(client.get_space_views(space_id))
            if sv:
                _add_view(sv, "espaço")
                continue

            # 2. Pastas do espaço (só chega aqui se não encontrou no nível espaço)
            try:
                folders = client.get_folders(space_id) or []
            except Exception:
                folders = []
            found_in_folder = False
            for folder in folders:
                fv = _find_bi_view_in_views(client.get_folder_views(folder["id"]))
                if fv:
                    _add_view(fv, f"pasta: {folder['name']}")
                    found_in_folder = True
                    continue

                # 3. Listas dentro da pasta (só se não achou na pasta)
                try:
                    lists_in_folder = client.get_lists_in_folder(folder["id"]) or []
                except Exception:
                    lists_in_folder = []
                for lst in lists_in_folder:
                    lv = _find_bi_view_in_views(client.get_list_views(lst["id"]))
                    if lv:
                        _add_view(lv, f"lista: {lst['name']}")

            if not found_in_folder:
                # 4. Listas soltas no espaço (fora de pastas)
                try:
                    lists_in_space = client.get_lists_in_space(space_id) or []
                except Exception:
                    lists_in_space = []
                for lst in lists_in_space:
                    lv = _find_bi_view_in_views(client.get_list_views(lst["id"]))
                    if lv:
                        _add_view(lv, f"lista: {lst['name']}")

    return bi_plan


def process_resumo_bi(client, bi_writer, space_name, view_name, view_id):
    """Extrai todas as tarefas da view Resumo BI e grava no bi_writer."""
    print(f"    [View] {space_name} / {view_name}")
    tasks = client.get_view_tasks(view_id)
    if not tasks:
        print("      → Sem tarefas.")
        return 0

    count = 0
    for task in tasks:
        if task.get("parent"):
            continue
        tis_data = {}
        try:
            tis_data = client.get_time_in_status(task["id"]) or {}
        except Exception:
            pass
        bi_writer.append_task(
            task,
            tis_data=tis_data,
            space_name=space_name,
            folder_name="",
            list_name=view_name,
        )
        count += 1

    print(f"      → {count} tarefas gravadas.")
    return count


def build_extraction_plan(client, args):
    """
    Fase de descoberta: percorre toda a estrutura do ClickUp e retorna os alvos
    sem processar nada. Retorna (plan, loose_tasks).

    plan: lista de tuplas (team_name, space_name, folder_name, list_name, list_id)
    loose_tasks: lista de tuplas (team_name, task_dict) — tarefas soltas compartilhadas
    """
    plan = []
    loose_tasks = []
    seen_list_ids = set()

    def _add(team_name, space_name, folder_name, list_name, list_id):
        if list_id not in seen_list_ids:
            seen_list_ids.add(list_id)
            plan.append((team_name, space_name, folder_name, list_name, list_id))

    teams = client.get_teams()
    if not teams:
        return plan, loose_tasks

    for team in teams:
        team_id = team['id']
        team_name = team['name']

        if args.workspace and args.workspace != "Todos" and args.workspace != team_id:
            continue

        spaces = client.get_spaces(team_id)
        selected_ids = set(filter(None, args.space_ids.split(","))) if args.space_ids else set()
        print(f"  Escaneando {len(spaces)} espaço(s)...")
        for space in spaces:
            if selected_ids and space['id'] not in selected_ids:
                continue
            space_name = space['name']
            print(f"    [Space] {space_name}")

            for lst in client.get_lists_in_space(space['id']):
                if _sprint_matches(lst['name'], args.sprint_filter):
                    _add(team_name, space_name, None, lst['name'], lst['id'])

            folders = client.get_folders(space['id'])
            for folder in folders:
                print(f"      [Pasta] {folder['name']} ...")
                for lst in client.get_lists_in_folder(folder['id']):
                    if _sprint_matches(lst['name'], args.sprint_filter):
                        _add(team_name, space_name, folder['name'], lst['name'], lst['id'])

        print("  Buscando itens compartilhados...")
        shared = client.get_shared_items(team_id)
        for folder in shared.get("folders", []):
            print(f"    [Compartilhado] {folder.get('name', folder['id'])} ...")
            for lst in client.get_lists_in_folder(folder['id']):
                if _sprint_matches(lst['name'], args.sprint_filter):
                    _add(team_name, "Compartilhados_Comigo", folder['name'], lst['name'], lst['id'])
        for lst in shared.get("lists", []):
            if _sprint_matches(lst['name'], args.sprint_filter):
                _add(team_name, "Compartilhados_Comigo", None, lst['name'], lst['id'])
        for task in shared.get("tasks", []):
            loose_tasks.append((team_name, task))

    return plan, loose_tasks


def print_extraction_plan(plan, loose_tasks):
    """Imprime no console a lista completa de sprints/listas que serão extraídas."""
    print("\n" + "=" * 70)
    print(">>> PRÉ-VISUALIZAÇÃO — LISTAS QUE SERÃO PROCESSADAS")
    print("=" * 70)

    if not plan and not loose_tasks:
        print("  Nenhuma lista encontrada com os filtros atuais.")
        print("=" * 70 + "\n")
        return

    current_team, current_space = None, None
    for i, (team_name, space_name, folder_name, list_name, _) in enumerate(plan, 1):
        if team_name != current_team:
            current_team = team_name
            current_space = None
            print(f"\n  [Workspace] {current_team}")
        if space_name != current_space:
            current_space = space_name
            print(f"    [Space] {current_space}")
        folder_prefix = f"[{folder_name}]  " if folder_name else ""
        print(f"      {i:>3}. {folder_prefix}{list_name}")

    if loose_tasks:
        print(f"\n  + {len(loose_tasks)} tarefa(s) solta(s) compartilhada(s) diretamente")

    print(f"\n  TOTAL: {len(plan)} lista(s) encontrada(s).")
    print("=" * 70 + "\n")


def post_process_empty_shells(client, writer, output_mode="completo"):
    if output_mode not in ("completo", "csv_json"):
        return
    base_path = writer.base_dir
    if not os.path.exists(base_path):
        return
    for root, _, files in os.walk(base_path):
        folder_name = os.path.basename(root)
        if folder_name.startswith("[") and "]" in folder_name:
            if not any(f.endswith("(RESUMO GERAL).pdf") for f in files):
                task_id = folder_name.split("]")[0].replace("[", "")
                try:
                    task = client.get_task(task_id)
                    if task:
                        comments = client.get_task_comments(task_id) if output_mode == "completo" else []
                        if output_mode == "completo":
                            writer.save_human_readable_pdf(root, task, comments)
                        writer.save_json(root, "tarefa_original.json", task)
                        writer.save_json(root, "comentarios.json", comments)
                except Exception:
                    pass


def process_single_task(client, writer, downloader, bi_writer, space_name, folder_name, list_name, task, tasks_dict, output_mode="completo"):
    if task.get("parent"):
        return  # Apenas tarefas de nível superior, igual ao Resumo BI
    try:
        task_id = task.get("id")
        task_name = task.get("name")
        print(f"          [Tarefa] {task_name[:50]}")
        parent_id = task.get("parent")
        parent_name = None
        parent_chain = []

        if parent_id and tasks_dict:
            current_pid = parent_id
            while current_pid and current_pid in tasks_dict:
                p_task = tasks_dict[current_pid]
                parent_chain.insert(0, (current_pid, p_task.get('name', 'Tarefa_Pai')))
                current_pid = p_task.get("parent")

        if parent_id and tasks_dict and parent_id in tasks_dict:
            parent_name = tasks_dict[parent_id].get('name')

        task['_local_subtasks_count'] = sum(
            1 for t in tasks_dict.values() if t.get('parent') == task_id
        ) if tasks_dict else 0

        sub_attachments_count = 0
        if tasks_dict:
            for t_obj in tasks_dict.values():
                if t_obj.get("parent") == task_id:
                    s_atts = t_obj.get("attachments", [])
                    sub_attachments_count += len(s_atts) if isinstance(s_atts, list) else 0



        task_folder_path = writer.create_hierarchy(
            space_name=space_name,
            folder_name=folder_name,
            list_name=list_name,
            task_id=task_id,
            task_name=task_name,
            parent_id=parent_id,
            parent_name=parent_name,
            parent_chain=parent_chain
        )

        comments = []
        try:
            comments = client.get_task_comments(task_id)
        except Exception as e:
            print(f"        [Aviso] Falha ao ler comentarios: {e}")

        if output_mode == "completo":
            writer.save_human_readable_pdf(task_folder_path, task, comments)
            writer.save_human_readable_log(task_folder_path, task, comments)

            if parent_id and tasks_dict and parent_id in tasks_dict:
                try:
                    p_task = tasks_dict[parent_id]
                    p_task['_local_subtasks_count'] = sum(
                        1 for t in tasks_dict.values() if t.get('parent') == parent_id
                    )
                    p_path = writer.create_hierarchy(
                        space_name=space_name,
                        folder_name=folder_name,
                        list_name=list_name,
                        task_id=parent_id,
                        task_name=p_task.get('name', 'Pai')
                    )
                    writer.save_human_readable_pdf(p_path, p_task, [])
                except Exception:
                    pass

        writer.save_json(task_folder_path, "tarefa_original.json", task)
        writer.save_json(task_folder_path, "comentarios.json", comments)

        total_anexos = 0
        if output_mode == "completo":
            t_attachs = downloader.extract_attachments_from_task(task)
            c_attachs = downloader.extract_attachments_from_comments(comments)
            total_anexos = len(t_attachs) + len(c_attachs)

            if total_anexos > 0:
                att_folder = os.path.join(task_folder_path, "Anexos")
                os.makedirs(att_folder, exist_ok=True)
                for att in t_attachs:
                    if att.get('name'):
                        print(f"            [Anexo T] {att['name'][:40]}...")
                    downloader.download_attachment(att['url'], att['name'], att_folder)
                for att in c_attachs:
                    if att.get('name'):
                        print(f"            [Anexo C] {att['name'][:40]}...")
                    downloader.download_attachment(att['url'], att['name'], att_folder)
        else:
            total_anexos = len(task.get('attachments', []))

        bi_writer.append_task(task, space_name=space_name, folder_name=folder_name, list_name=list_name)

    except Exception as e:
        print(f"        [ERRO] Falha ao processar a tarefa {task.get('id', '?')}: {e}")


def process_list(client, writer, downloader, bi_writer, space_name, folder_name, list_name, list_id, status_filter, date_gt, _is_pilot, output_mode="completo"):
    print(f"      [List] {list_name}")

    tasks = client.get_tasks(list_id, subtasks=False, date_updated_gt=date_gt)
    if not tasks:
        print("        -> Lista vazia/sem atualizações.")
        return False

    tasks_dict = {t.get('id'): t for t in tasks}
    processed_ids = set()

    pending_parents = [t.get("parent") for t in tasks if t.get("parent") and t.get("parent") not in tasks_dict]
    while pending_parents:
        p_id = pending_parents.pop(0)
        if not p_id or p_id in tasks_dict:
            continue
        p_task = client.get_task(p_id) or {
            "id": p_id,
            "name": f"TAREFA-PAI RESTRITA ({p_id})",
            "status": {"status": "Sem Permissão"},
            "description": "Dados ocultados por restrição de privacidade no ClickUp.",
            "custom_fields": [],
            "attachments": []
        }
        tasks_dict[p_id] = p_task
        gp_id = p_task.get("parent")
        if gp_id and gp_id not in tasks_dict:
            pending_parents.append(gp_id)

    valid_tasks_ids = set()
    for task in tasks:
        if status_filter != "Todas":
            st_type = task.get("status", {}).get("type", "custom").lower()
            if status_filter == "Somente Abertas" and st_type in ["closed", "done"]:
                continue
            if status_filter == "Somente Fechadas" and st_type not in ["closed", "done"]:
                continue
        valid_tasks_ids.add(task.get("id"))

    pending_children = list(valid_tasks_ids)
    while pending_children:
        c_id = pending_children.pop(0)
        c_task = tasks_dict.get(c_id)
        if not c_task:
            continue
        for st in c_task.get("subtasks", []) if isinstance(c_task.get("subtasks"), list) else []:
            st_id = st.get("id") if isinstance(st, dict) else st
            if not isinstance(st_id, str):
                continue
            if st_id not in tasks_dict:
                st_obj = client.get_task(st_id)
                if st_obj:
                    tasks_dict[st_id] = st_obj
            if st_id not in valid_tasks_ids:
                valid_tasks_ids.add(st_id)
                pending_children.append(st_id)

    all_to_process = list(valid_tasks_ids) + [
        t.get('id') for t in tasks_dict.values() if t.get('id') not in valid_tasks_ids
    ]
    valid_count = 0
    for task_id in all_to_process:
        t = tasks_dict.get(task_id)
        if t and task_id not in processed_ids:
            valid_count += 1
            process_single_task(client, writer, downloader, bi_writer,
                                space_name, folder_name, list_name, t, tasks_dict, output_mode)
            processed_ids.add(task_id)

    if valid_count > 0:
        print(f"        -> {valid_count} tarefas/subtarefas processadas em '{list_name}'.")
    return True


def run_agendado():
    """Execução silenciosa disparada pelo Agendador de Tarefas do Windows."""
    import json
    from dotenv import load_dotenv

    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

    env_path = os.path.join(exe_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)

    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("[Agendado] ERRO: CLICKUP_API_TOKEN nao encontrado.")
        sys.exit(1)

    config_path = os.path.join(exe_dir, "agendamento.json")
    if not os.path.exists(config_path):
        print("[Agendado] ERRO: agendamento.json nao encontrado.")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    # Verifica dia da semana
    _DIAS_MAP = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}
    dias_cfg = cfg.get("dias_semana", [])
    if dias_cfg:
        dia_atual = datetime.datetime.now().weekday()
        dias_num = [_DIAS_MAP[d] for d in dias_cfg if d in _DIAS_MAP]
        if dia_atual not in dias_num:
            print(f"[Agendado] Hoje nao e um dia configurado ({list(cfg['dias_semana'])}). Pulando.")
            sys.exit(0)

    # Verifica janela de horário
    hora_inicio = cfg.get("hora_inicio", "")
    hora_fim = cfg.get("hora_fim", "")
    if hora_inicio and hora_fim:
        try:
            now_time = datetime.datetime.now().time()
            h_ini = datetime.datetime.strptime(hora_inicio, "%H:%M").time()
            h_fim = datetime.datetime.strptime(hora_fim, "%H:%M").time()
            if not (h_ini <= now_time <= h_fim):
                print(f"[Agendado] Fora da janela de horario ({hora_inicio}–{hora_fim}). Pulando.")
                sys.exit(0)
        except ValueError:
            pass

    space_ids = cfg.get("space_ids", "")
    output_mode = "apenas_csv_api"  # agendamento sempre usa modo API
    output_dir = os.path.join(exe_dir, "Dados_BI_ClickUp")

    class _Args:
        pass

    args = _Args()
    args.workspace = ""
    args.space_ids = space_ids
    args.sprint_filter = ""
    args.status_filter = "Todas"
    args.output_mode = output_mode
    args.preview_only = False
    args.output_dir = output_dir
    args.date_gt = ""
    args.mode = 2

    print(f"[Agendado] Iniciando — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    client = ClickUpClient()

    bi_plan = _BI_VIEWS
    os.makedirs(output_dir, exist_ok=True)

    bi_writer = ExcelBIWriter(output_dir, suffix="Geral")
    for (space_name, view_name, view_id, *_) in bi_plan:
        process_resumo_bi(client, bi_writer, space_name, view_name, view_id)
    bi_writer.finalize_xlsx()

    try:
        from bigdata_ingestor import ingerir
        ingerir(output_dir)
    except Exception as e:
        print(f"  [BigData] Ingestao ignorada: {e}")

    print(f"[Agendado] Extracao concluida — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("[Agendado] Processo finalizado.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extrator ClickUp — ATI Pernambuco\n"
            "\n"
            "Variaveis de ambiente necessarias:\n"
            "  CLICKUP_API_TOKEN   Token da API do ClickUp (obrigatorio)\n"
            "\n"
            "Modos de extracao:\n"
            "  apenas_csv_api  Extrai tarefas das views 'Resumo BI' via API e gera CSV + XLSX\n"
            "  csv_json        Extrai todas as tarefas via API e gera JSON + XLSX\n"
            "  completo        PDF por tarefa + JSON + anexos + XLSX\n"
            "\n"
            "Exemplos:\n"
            "  python main.py --output_mode apenas_csv_api "
            "--space_ids 90131657451,90131683703 --output_dir /data/clickup/\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", type=int, default=2,
                        help="1=piloto (1 lista), 2=completo (padrao: 2)")
    parser.add_argument("--workspace", type=str, default="",
                        help="ID do workspace/team (opcional, usa todos se omitido)")
    parser.add_argument("--space_ids", type=str, default="",
                        help="IDs dos espacos separados por virgula (ex: 90131657451,90131683703)")
    parser.add_argument("--date_gt", type=str, default="",
                        help="Filtra tarefas atualizadas apos esta data (DD/MM/AAAA)")
    parser.add_argument("--sprint_filter", type=str, default="",
                        help="Filtra por nome de sprint/lista")
    parser.add_argument("--status_filter", type=str, default="Todas",
                        help="Filtra por status das tarefas (padrao: Todas)")
    parser.add_argument("--output_mode", type=str, default="completo",
                        choices=["completo", "csv_json", "apenas_csv_api"],
                        help="Modo de extracao (ver descricao acima)")
    parser.add_argument("--preview_only", action="store_true",
                        help="Lista os alvos encontrados sem extrair nada")
    parser.add_argument("--output_dir", type=str, default="",
                        help="Pasta de saida para os arquivos gerados")
    parser.add_argument("--wizard", action="store_true",
                        help="Modo assistente interativo (guia passo a passo)")
    args = parser.parse_args()

    if args.wizard:
        import cli_wizard
        cli_wizard.main()
        return

    # Carrega .env se existir (nao sobrescreve variaveis ja definidas no ambiente)
    try:
        from dotenv import load_dotenv
        _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(_env_path):
            load_dotenv(_env_path)
    except ImportError:
        pass

    token = os.environ.get("CLICKUP_API_TOKEN", "").strip("\"'")
    if not token:
        print("ERRO: CLICKUP_API_TOKEN nao definido.")
        print("  Defina via variavel de ambiente: export CLICKUP_API_TOKEN='pk_...'")
        print("  Ou crie um arquivo .env com: CLICKUP_API_TOKEN=pk_...")
        sys.exit(1)
    os.environ["CLICKUP_API_TOKEN"] = token

    is_pilot = (args.mode == 1)
    output_mode = args.output_mode
    client = ClickUpClient()

    def _bi_base_dir(subdir: str) -> str:
        if args.output_dir:
            return args.output_dir  # BigData/pipeline: usa o path exato, sem subpasta
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), "Dados_BI_ClickUp", subdir)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dados_BI_ClickUp", subdir)

    # ── MODO API: extração consolidada via API ─────────────────────────────────
    if output_mode == "apenas_csv_api":
        bi_plan = _BI_VIEWS

        if args.preview_only:
            for space_name, view_name, view_id in bi_plan:
                print(f"  → {space_name} / {view_name}  (id: {view_id})")
            return

        api_output_dir = _bi_base_dir("API")
        os.makedirs(api_output_dir, exist_ok=True)

        _inicio = time.time()
        _inicio_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        print(f"\n{'='*70}")
        print(f"  INICIO DA EXTRACAO (Resumo BI via API): {_inicio_str}")
        print(f"  Views a processar: {len(bi_plan)}")
        print(f"  Pasta de saida: {api_output_dir}")
        print(f"{'='*70}\n")

        bi_writer = ExcelBIWriter(api_output_dir, suffix=args.sprint_filter or "Geral")
        total_tarefas = 0
        for (space_name, view_name, view_id, *_) in bi_plan:
            total_tarefas += process_resumo_bi(client, bi_writer, space_name, view_name, view_id)
        bi_writer.finalize_xlsx()

        _fim_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        _total = _fmt_elapsed(time.time() - _inicio)
        print(f"\n{'='*70}")
        print(f"  EXTRACAO VIA API CONCLUIDA!")
        print(f"  Inicio : {_inicio_str}")
        print(f"  Fim    : {_fim_str}")
        print(f"  Duracao: {_total}")
        print(f"  Total de tarefas extraidas: {total_tarefas}")
        print(f"{'='*70}")

        # Ingestão automática no BigData PE (só se a biblioteca estiver disponível)
        try:
            from bigdata_ingestor import ingerir
            ingerir(api_output_dir)
        except Exception as e:
            print(f"  [BigData] Ingestão ignorada: {e}")

        return

    # ── DEMAIS MODOS: extração completa por listas ─────────────────────────────
    print("\n>>> Escaneando estrutura do ClickUp...")
    plan, loose_tasks = build_extraction_plan(client, args)
    print_extraction_plan(plan, loose_tasks)

    if args.preview_only:
        return

    if not plan and not loose_tasks:
        print("Nenhum alvo encontrado. Verifique os filtros e o token.")
        return

    # --- FASE 2: EXTRAÇÃO ---
    writer = DataWriter(base_dir=args.output_dir if args.output_dir else None)
    downloader = AttachmentDownloader(headers=client.headers)
    bi_writer = ExcelBIWriter(writer.base_dir, suffix=args.sprint_filter or "Geral")

    _inicio = time.time()
    _inicio_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n{'='*70}")
    print(f"  INICIO DA EXTRACAO: {_inicio_str}")
    print(f"  Total de listas a processar: {len(plan)} | Tarefas soltas: {len(loose_tasks)}")
    print(f"{'='*70}\n")

    _listas_ok = 0
    current_team, current_space = None, None
    for (team_name, space_name, folder_name, list_name, list_id) in plan:
        if team_name != current_team:
            current_team = team_name
            print(f"\n[Workspace] {team_name}")
        if space_name != current_space:
            current_space = space_name
            print(f"  [Space] {space_name}")
        if folder_name:
            print(f"    [Folder] {folder_name}")

        success = process_list(client, writer, downloader, bi_writer,
                               space_name, folder_name, list_name, list_id,
                               args.status_filter, args.date_gt, is_pilot, output_mode)
        if success:
            _listas_ok += 1
        elapsed = _fmt_elapsed(time.time() - _inicio)
        print(f"        [Tempo decorrido: {elapsed} | Listas concluidas: {_listas_ok}]")
        if _pilot_done(is_pilot, success, client, writer, output_mode):
            return

    for (team_name, task) in loose_tasks:
        tasks_dict = {task['id']: task}
        process_single_task(client, writer, downloader, bi_writer,
                            "Compartilhados_Comigo", None, "Tarefas_Soltas",
                            task, tasks_dict, output_mode)
        if _pilot_done(is_pilot, True, client, writer, output_mode):
            return

    post_process_empty_shells(client, writer, output_mode)
    bi_writer.finalize_xlsx()

    _fim_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    _total = _fmt_elapsed(time.time() - _inicio)
    print(f"\n{'='*70}")
    print(f"  EXTRACAO COMPLETA FINALIZADA COM SUCESSO!")
    print(f"  Inicio : {_inicio_str}")
    print(f"  Fim    : {_fim_str}")
    print(f"  Duracao: {_total}")
    print(f"  Listas processadas com dados: {_listas_ok} / {len(plan)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
