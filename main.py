import os
import sys
import argparse
from clickup_client import ClickUpClient
from data_writer import DataWriter
from attachment_downloader import AttachmentDownloader
from excel_writer import ExcelBIWriter

def post_process_empty_shells(client, writer):
    base_path = writer.base_dir
    if not os.path.exists(base_path): return
    for root, dirs, files in os.walk(base_path):
        folder_name = os.path.basename(root)
        if folder_name.startswith("[") and "]" in folder_name:
            if not any(f.endswith("(RESUMO GERAL).pdf") for f in files):
                task_id = folder_name.split("]")[0].replace("[", "")
                try:
                    task = client.get_task(task_id)
                    if task:
                        comments = client.get_task_comments(task_id)
                        writer.save_human_readable_pdf(root, task, comments)
                        writer.save_json(root, "tarefa_original.json", task)
                        writer.save_json(root, "comentarios.json", comments)
                except Exception:
                    pass

def process_single_task(client, writer, downloader, bi_writer, space_name, folder_name, list_name, task, tasks_dict):
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
            
        task['_local_subtasks_count'] = sum(1 for t in tasks_dict.values() if t.get('parent') == task_id) if tasks_dict else 0
        
        # 1. Cria a Pasta Física com hierarquia completa (V8.20+)
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
        
        # 2. Extrai Comentários e Histórico (try/catch protetor)
        comments = []
        try:
            comments = client.get_task_comments(task_id)
        except Exception as e:
            print(f"        [Aviso] Falha ao ler comentarios: {e}")
            
        # 3. GERA O RELATÓRIO CORPORATIVO EM PDF E TXT
        task_pdf_path = writer.save_human_readable_pdf(task_folder_path, task, comments)
        writer.save_human_readable_log(task_folder_path, task, comments)
        
        # [V8.27] FORÇA BRUTA: Se esta tarefa for uma sub-tarefa, garante que o PDF do PAI seja criado AGORA MESMO
        # na pasta do PAI, prevenindo qualquer falha de paginação ou escape de filtros do ClickUp.
        if parent_id and tasks_dict and parent_id in tasks_dict:
            try:
                p_task = tasks_dict[parent_id]
                
                # V8.28: Garante que a contagem de filhas apareça no PDF do Pai gerado na base da força bruta!
                p_task['_local_subtasks_count'] = sum(1 for temp_t in tasks_dict.values() if temp_t.get('parent') == parent_id)
                
                p_path = writer.create_hierarchy(
                    space_name=space_name,
                    folder_name=folder_name,
                    list_name=list_name,
                    task_id=parent_id,
                    task_name=p_task.get('name', 'Pai')
                )
                # Injeta silenciosamente o Resumo Geral do pai, mesmo se a rotina principal esquecê-lo.
                writer.save_human_readable_pdf(p_path, p_task, [])
            except Exception: pass
        
        # 3.5 RESTAURAÇÃO DOS METADADOS RAW (Cruciais para auditoria)
        writer.save_json(task_folder_path, "tarefa_original.json", task)
        writer.save_json(task_folder_path, "comentarios.json", comments)
        
        # 4. DOWNLOAD DE ANEXOS DA TAREFA E DOS COMENTÁRIOS
        t_attachs = downloader.extract_attachments_from_task(task)
        c_attachs = downloader.extract_attachments_from_comments(comments)
        
        total_anexos = len(t_attachs) + len(c_attachs)
        has_attachments = total_anexos > 0
        
        if has_attachments:
            # Cria a pasta explícita de anexos para não misturar com o PDF
            att_folder = os.path.join(task_folder_path, "Anexos")
            if not os.path.exists(att_folder):
                os.makedirs(att_folder)
                
            if t_attachs:
                for att in t_attachs:
                    if att.get('name'):
                        print(f"            [Anexo T] {att['name'][:40]}...")
                    downloader.download_attachment(att['url'], att['name'], att_folder)
                    
            if c_attachs:
                for att in c_attachs:
                    if att.get('name'):
                        print(f"            [Anexo C] {att['name'][:40]}...")
        # 5. DOWNLOAD DE ANEXOS DOS COMENTÁRIOS E HISTÓRICO... (Feito acima integrando com C_Attachs)
        
        # 6. CONTAGEM INTELIGENTE DE ANEXOS EM SUBTAREFAS DIRETAS (Apenas para o BI)
        sub_attachments_count = 0
        if tasks_dict:
            for t_id, t_obj in tasks_dict.items():
                if t_obj.get("parent") == task_id:
                    s_atts = t_obj.get("attachments", [])
                    sub_attachments_count += len(s_atts) if isinstance(s_atts, list) else 0

        # 7. INJETA LINHA NO RELATÓRIO DO POWER BI COM A CONTAGEM REAL E COMPLETA
        bi_writer.append_task(task, space_name, folder_name, list_name, total_anexos, sub_attachments_count)
                
    except Exception as e:
        print(f"        [ERRO] Falha ao processar a tarefa {task.get('id', '?')}: {e}")

def process_list(client, writer, downloader, bi_writer, space_name, folder_name, list_name, list_id, status_filter, date_gt, is_pilot):
    print(f"      [List] {list_name}")
    
    tasks = client.get_tasks(list_id, subtasks=True, date_updated_gt=date_gt)
    if not tasks:
        print("        -> Lista vazia/sem atualizações.")
        return False
        
    tasks_dict = {t.get('id'): t for t in tasks}
    valid_count = 0
    processed_ids = set()
    
    # 1. PRÉ-FETCH DE TODOS OS PAIS (Para garantir que as sub-tarefas saibam o NOME REAL do Pai)
    pending_parents = []
    for task in tasks:
        p_id = task.get("parent")
        if p_id and p_id not in tasks_dict:
            pending_parents.append(p_id)
            
    while pending_parents:
        p_id = pending_parents.pop(0)
        if not p_id or p_id in tasks_dict:
            continue
            
        p_task = client.get_task(p_id)
        if not p_task:
            p_task = {
                "id": p_id,
                "name": f"TAREFA-PAI RESTRITA ({p_id})",
                "status": {"status": "Sem Permissão"},
                "description": "Os dados originais desta tarefa estão ocultados por restrição de privacidade no ClickUp. Você extraiu a(s) subtarefa(s) que você detém acesso.\nAs subtarefas estarão na pasta ./Subtarefas desta hierarquia.",
                "custom_fields": [],
                "attachments": []
            }
        
        tasks_dict[p_id] = p_task
        
        gp_id = p_task.get("parent")
        if gp_id and gp_id not in tasks_dict:
            pending_parents.append(gp_id)

    # 2. SELEÇÃO PRIMÁRIA E CADEIA DE FILHOS (FORÇA BRUTA DESCENDENTE)
    # Primeiro escolhemos as Tarefas que bateram exatamente com o filtro escolhido
    valid_tasks_ids = set()
    for task in tasks:
        if status_filter != "Todas":
            st_type = task.get("status", {}).get("type", "custom").lower()
            if status_filter == "Somente Abertas" and st_type in ["closed", "done"]:
                continue
            if status_filter == "Somente Fechadas" and st_type not in ["closed", "done"]:
                continue
        valid_tasks_ids.add(task.get("id"))
        
    # Agora OBRIGAMOS que toda Subtarefa (Mesmo Fechada/Sem Sprint) de uma tarefa válida, seja puxada pra pasta!
    pending_children = list(valid_tasks_ids)
    while pending_children:
        c_id = pending_children.pop(0)
        c_task = tasks_dict.get(c_id)
        if not c_task:
            continue
            
        if "subtasks" in c_task and isinstance(c_task["subtasks"], list):
            for st in c_task["subtasks"]:
                st_id = st.get("id") if isinstance(st, dict) else st
                if not isinstance(st_id, str): continue
                
                # Se o filho estiver faltando na memória, busca com força bruta!
                if st_id not in tasks_dict:
                    st_obj = client.get_task(st_id)
                    if st_obj:
                        tasks_dict[st_id] = st_obj
                        
                if st_id not in valid_tasks_ids:
                    valid_tasks_ids.add(st_id)
                    pending_children.append(st_id)
                    
    # 3. PROCESSA AS TAREFAS VÁLIDAS E SEUS DESCENDENTES
    for task_id in valid_tasks_ids:
        t = tasks_dict.get(task_id)
        if t and task_id not in processed_ids:
            valid_count += 1
            process_single_task(client, writer, downloader, bi_writer, space_name, folder_name, list_name, t, tasks_dict)
            processed_ids.add(task_id)

    # 4. PROCESSA OS PAIS RESGATADOS (Apenas Pais vitais para a estrutura que foram forçados)
    resgatados = [t for t in tasks_dict.values() if t.get('id') not in processed_ids]
    for p_task in resgatados:
        valid_count += 1
        process_single_task(client, writer, downloader, bi_writer, space_name, folder_name, list_name, p_task, tasks_dict)
        processed_ids.add(p_task.get('id'))
        
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
    args = parser.parse_args()

    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("Erro: CLICKUP_API_TOKEN nao encontrado.")
        sys.exit(1)

    is_pilot = (args.mode == 1)
    client = ClickUpClient()
    writer = DataWriter()
    downloader = AttachmentDownloader(headers=client.headers)
    
    sprint_suffix = args.sprint_filter if args.sprint_filter else "Geral"
    bi_writer = ExcelBIWriter(writer.base_dir, suffix=sprint_suffix)

    try:
        teams = client.get_teams()
        if not teams:
            print("Nenhum Workspace encontrado. O Token é invalido.")
            sys.exit(1)

        for team in teams:
            team_id = team['id']
            team_name = team['name']

            if args.workspace and args.workspace != "Todos" and args.workspace != team_id:
                continue

            print(f"\n[Workspace] {team_name} (ID: {team_id})")

            spaces = client.get_spaces(team_id)
            if spaces:
                for space in spaces:
                    space_name = space['name']
                    print(f"  [Space] {space_name}")

                    # Listas raizes
                    for lst in client.get_lists_in_space(space['id']):
                        if args.sprint_filter and args.sprint_filter.lower() not in lst['name'].lower():
                            continue
                        success = process_list(client, writer, downloader, bi_writer, space_name, None, lst['name'], lst['id'], args.status_filter, args.date_gt, is_pilot)
                        if is_pilot and success:
                            post_process_empty_shells(client, writer)
                            print("[PILOTO FINALIZADO]")
                            return

                    # Pastas
                    for folder in client.get_folders(space['id']):
                        folder_name = folder['name']
                        print(f"    [Folder] {folder_name}")
                        for lst in client.get_lists_in_folder(folder['id']):
                            if args.sprint_filter and args.sprint_filter.lower() not in lst['name'].lower():
                                continue
                            success = process_list(client, writer, downloader, bi_writer, space_name, folder_name, lst['name'], lst['id'], args.status_filter, args.date_gt, is_pilot)
                            if is_pilot and success:
                                post_process_empty_shells(client, writer)
                                print("[PILOTO FINALIZADO]")
                                return

            # Shared
            shared = client.get_shared_items(team_id)
            if shared:
                for folder in shared.get("folders", []):
                    folder_name = folder['name']
                    for lst in client.get_lists_in_folder(folder['id']):
                        if args.sprint_filter and args.sprint_filter.lower() not in lst['name'].lower():
                            continue
                        success = process_list(client, writer, downloader, bi_writer, "Compartilhados_Comigo", folder_name, lst['name'], lst['id'], args.status_filter, args.date_gt, is_pilot)
                        if is_pilot and success:
                            post_process_empty_shells(client, writer)
                            return
                for lst in shared.get("lists", []):
                    if args.sprint_filter and args.sprint_filter.lower() not in lst['name'].lower():
                        continue
                    success = process_list(client, writer, downloader, bi_writer, "Compartilhados_Comigo", None, lst['name'], lst['id'], args.status_filter, args.date_gt, is_pilot)
                    if is_pilot and success:
                        post_process_empty_shells(client, writer)
                        return
                tasks = shared.get("tasks", [])
                if tasks:
                    tasks_dict = {t['id']: t for t in tasks}
                    for task in tasks:
                        process_single_task(client, writer, downloader, bi_writer, "Compartilhados_Comigo", None, "Tarefas_Soltas", task, tasks_dict)
                        if is_pilot:
                            post_process_empty_shells(client, writer)
                            return

        post_process_empty_shells(client, writer)
        print("\nEXTRAÇÃO COMPLETA FINALIZADA COM SUCESSO!")
    except Exception as e:
        print(f"\n[ERRO FATAL NO MAIN] {e}")

if __name__ == "__main__":
    main()
