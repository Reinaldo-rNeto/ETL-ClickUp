import os
import sys
import argparse
from clickup_client import ClickUpClient
from data_writer import DataWriter
from attachment_downloader import AttachmentDownloader
from excel_writer import ExcelBIWriter


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


def build_extraction_plan(client, args):
    """
    Fase de descoberta: percorre toda a estrutura do ClickUp e retorna os alvos
    sem processar nada. Retorna (plan, loose_tasks).

    plan: lista de tuplas (team_name, space_name, folder_name, list_name, list_id)
    loose_tasks: lista de tuplas (team_name, task_dict) — tarefas soltas compartilhadas
    """
    plan = []
    loose_tasks = []

    teams = client.get_teams()
    if not teams:
        return plan, loose_tasks

    for team in teams:
        team_id = team['id']
        team_name = team['name']

        if args.workspace and args.workspace != "Todos" and args.workspace != team_id:
            continue

        for space in client.get_spaces(team_id):
            space_name = space['name']
            for lst in client.get_lists_in_space(space['id']):
                if _sprint_matches(lst['name'], args.sprint_filter):
                    plan.append((team_name, space_name, None, lst['name'], lst['id']))
            for folder in client.get_folders(space['id']):
                for lst in client.get_lists_in_folder(folder['id']):
                    if _sprint_matches(lst['name'], args.sprint_filter):
                        plan.append((team_name, space_name, folder['name'], lst['name'], lst['id']))

        shared = client.get_shared_items(team_id)
        for folder in shared.get("folders", []):
            for lst in client.get_lists_in_folder(folder['id']):
                if _sprint_matches(lst['name'], args.sprint_filter):
                    plan.append((team_name, "Compartilhados_Comigo", folder['name'], lst['name'], lst['id']))
        for lst in shared.get("lists", []):
            if _sprint_matches(lst['name'], args.sprint_filter):
                plan.append((team_name, "Compartilhados_Comigo", None, lst['name'], lst['id']))
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
    for root, dirs, files in os.walk(base_path):
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

        if output_mode == "apenas_csv":
            bi_writer.append_task(task, space_name, folder_name, list_name,
                                  len(task.get('attachments', [])), sub_attachments_count)
            return

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

        bi_writer.append_task(task, space_name, folder_name, list_name, total_anexos, sub_attachments_count)

    except Exception as e:
        print(f"        [ERRO] Falha ao processar a tarefa {task.get('id', '?')}: {e}")


def process_list(client, writer, downloader, bi_writer, space_name, folder_name, list_name, list_id, status_filter, date_gt, is_pilot, output_mode="completo"):
    print(f"      [List] {list_name}")

    tasks = client.get_tasks(list_id, subtasks=True, date_updated_gt=date_gt)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=int, default=2)
    parser.add_argument("--workspace", type=str, default="")
    parser.add_argument("--date_gt", type=str, default="")
    parser.add_argument("--sprint_filter", type=str, default="")
    parser.add_argument("--status_filter", type=str, default="Todas")
    parser.add_argument("--output_mode", type=str, default="completo",
                        choices=["completo", "csv_json", "apenas_csv"])
    parser.add_argument("--preview_only", action="store_true",
                        help="Apenas lista os alvos sem extrair nada")
    args = parser.parse_args()

    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("Erro: CLICKUP_API_TOKEN nao encontrado.")
        sys.exit(1)

    is_pilot = (args.mode == 1)
    output_mode = args.output_mode
    client = ClickUpClient()

    # --- FASE 1: DESCOBERTA ---
    print("\n>>> Escaneando estrutura do ClickUp...")
    plan, loose_tasks = build_extraction_plan(client, args)
    print_extraction_plan(plan, loose_tasks)

    if args.preview_only:
        return

    if not plan and not loose_tasks:
        print("Nenhum alvo encontrado. Verifique os filtros e o token.")
        return

    # --- FASE 2: EXTRAÇÃO ---
    writer = DataWriter()
    downloader = AttachmentDownloader(headers=client.headers)
    bi_writer = ExcelBIWriter(writer.base_dir, suffix=args.sprint_filter or "Geral")

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
    print("\nEXTRAÇÃO COMPLETA FINALIZADA COM SUCESSO!")


if __name__ == "__main__":
    main()
