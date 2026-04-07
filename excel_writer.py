import csv
import os
from datetime import datetime

class ExcelBIWriter:
    def __init__(self, base_dir, suffix="Geral"):
        safe_suffix = ''.join(c for c in suffix if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        if not safe_suffix: safe_suffix = "Consolidado"
        filename = f"Relatorio_BI_{safe_suffix}.csv"
        
        self.filepath = os.path.join(base_dir, filename)
        self.headers = [
            "ID da Tarefa", "Nome da Tarefa", "Status", "Prioridade", 
            "Data de Criacao", "Data de Atualizacao", "Data de Conclusao",
            "Tempo Gasto (Horas)", "Tempo Estimado (Horas)", 
            "Espaco", "Pasta", "Lista (Sprint)", "ID do Pai (Se Subtarefa)", 
            "Criador", "Responsaveis", "Envolvidos", "Tags", "Campos Customizados",
            "Qtd Subtarefas", "Qtd Anexos Originais", "Qtd Anexos (Subtarefas)", "URL Original"
        ]
        self.ensure_initialized()

    def ensure_initialized(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        # Se não existe, cria do zero com cabeçalhos.
        if not os.path.exists(self.filepath):
            with open(self.filepath, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(self.headers)

    def _format_date(self, timestamp_ms):
        if not timestamp_ms:
            return ""
        try:
            return datetime.fromtimestamp(int(timestamp_ms) / 1000).strftime('%d/%m/%Y %H:%M:%S')
        except:
            return ""

    def _format_hours(self, ms):
        if not ms:
            return "0"
        try:
            # PowerBI entende a vírgula como decimal na configuração PT-BR
            return str(round(int(ms) / 3600000, 2)).replace('.', ',')
        except:
            return "0"

    def _clean_text(self, text):
        if not text:
            return ""
        # Limpa quebras de linha e separadores de coluna do texto sujo do ClickUp
        text = str(text).replace(';', ',').replace('\n', ' ').replace('\r', '')
        # Blinda contra caracteres alienígenas que corrompem visualização de relatórios
        return ''.join(c for c in text if ord(c) < 10000)

    def append_task(self, task, space_name, folder_name, list_name, total_anexos=0, sub_attachments_count=0):
        try:
            status = task.get('status', {}).get('status', '')
            priority = task.get('priority', {})
            priority_val = priority.get('priority', '') if isinstance(priority, dict) else ''
            
            creator = task.get('creator', {}).get('username', '')
            
            assignees = [a.get('username', '') for a in task.get('assignees', [])]
            assignees_str = ", ".join(assignees)
            
            tags = [t.get('name', '') for t in task.get('tags', [])]
            tags_str = ", ".join(tags)
            
            envolvidos_list = []
            cfields = []
            for cf in task.get('custom_fields', []):
                name = cf.get('name', '')
                val = cf.get('value')
                
                if val is not None:
                    # Trata listas (ex: múltiplos usuários em Envolvidos)
                    if isinstance(val, list):
                        if len(val) > 0 and isinstance(val[0], dict) and 'username' in val[0]:
                            clean_val = ", ".join([v.get('username', '') for v in val])
                        else:
                            clean_val = ", ".join([str(v) for v in val])
                    # Trata objeto único de usuário
                    elif isinstance(val, dict) and 'username' in val:
                        clean_val = val.get('username', '')
                    else:
                        clean_val = str(val)
                        
                    if name.lower().strip() == 'envolvidos':
                        envolvidos_list.append(clean_val)
                    else:
                        cfields.append(f"{name}: {clean_val}")
                        
            envolvidos_str = ", ".join(envolvidos_list)
            cfields_str = " | ".join(cfields)

            # Contadores de auditoria (Puxando a Força Bruta)
            if '_local_subtasks_count' in task:
                sub_count = task['_local_subtasks_count']
            else:
                s = task.get('subtasks', [])
                sub_count = len(s) if isinstance(s, list) else 0
                
            row = [
                task.get('id', ''),
                self._clean_text(task.get('name', '')),
                self._clean_text(status).upper(),
                self._clean_text(priority_val).upper(),
                self._format_date(task.get('date_created')),
                self._format_date(task.get('date_updated')),
                self._format_date(task.get('date_closed')),
                self._format_hours(task.get('time_spent')),
                self._format_hours(task.get('time_estimate')),
                self._clean_text(space_name),
                self._clean_text(folder_name),
                self._clean_text(list_name),
                self._clean_text(task.get('parent', '')),
                self._clean_text(creator),
                self._clean_text(assignees_str),
                self._clean_text(envolvidos_str),
                self._clean_text(tags_str),
                self._clean_text(cfields_str),
                str(sub_count),
                str(total_anexos),
                str(sub_attachments_count),
                self._clean_text(task.get('url', ''))
            ]
            
            with open(self.filepath, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(row)
        except Exception as e:
            print(f"        [Aviso CSV] Não foi possível injetar a linha do Id {task.get('id')} no BI: {e}")
