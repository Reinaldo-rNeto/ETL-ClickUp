import os
import json
import sys
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib import colors

class DataWriter:
    def __init__(self, base_dir=None):
        if base_dir is None:
            if getattr(sys, 'frozen', False):
                self.base_dir = os.path.join(os.path.dirname(sys.executable), "Dados_Extraidos_ClickUp")
            else:
                self.base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dados_Extraidos_ClickUp")
        else:
            self.base_dir = base_dir
            
        self.base_dir = os.path.abspath(self.base_dir)
        # Windows MAX_PATH bypass mágico ("\\?\")
        if os.name == 'nt' and not self.base_dir.startswith('\\\\?\\'):
            self.base_dir = '\\\\?\\' + self.base_dir
            
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def _sanitize_name(self, name, max_len=65):
        """Limpa o nome para que seja seguro usar como pasta/arquivo no Windows"""
        if not name:
            return "Sem_Nome"
        invalid_chars = '<>:"/\\|?*\n\r\t'
        for char in invalid_chars:
            name = name.replace(char, "_")
            
        name = name.strip()
        
        # Encurtador inteligente Anti-MaxPath (260 chars) do Windows Explorer
        if len(name) > max_len:
            name = name[:max_len].strip() + "_"
            
        # Retira os pontos finais do nome pq o Windows oculta perversamente e acusa FileNotFoundError!
        while name.endswith('.'):
            name = name[:-1]
            
        if not name.strip():
            return "Sem_Nome_Valido"
            
        return name.strip()

    def create_hierarchy(self, space_name, folder_name=None, list_name=None, task_id=None, task_name=None, parent_id=None, parent_name=None, parent_chain=None):
        """
        Gera e certifica-se de que o caminho físico para a árvore informada existe.
        Retorna a string do caminho (path) absoluto/relativo criado.
        """
        path = os.path.join(self.base_dir, self._sanitize_name(space_name))
        
        if folder_name:
            path = os.path.join(path, self._sanitize_name(folder_name))
        else:
            path = os.path.join(path, "Listas_Sem_Pasta")
            
        if list_name:
            path = os.path.join(path, self._sanitize_name(list_name))
            
        if parent_chain:
            for p_id, p_name in parent_chain:
                parent_folder = f"[{p_id}] {self._sanitize_name(p_name or 'Tarefa_Pai')}"
                path = os.path.join(path, parent_folder, "Subtarefas")
        elif parent_id:
            parent_folder = f"[{parent_id}] {self._sanitize_name(parent_name or 'Tarefa_Pai')}"
            path = os.path.join(path, parent_folder, "Subtarefas")
            
        if task_id and task_name:
            task_folder = f"[{task_id}] {self._sanitize_name(task_name)}"
            path = os.path.join(path, task_folder)

        os.makedirs(path, exist_ok=True)
        return path

    def save_json(self, path, filename, data):
        """Salva dicionário/lista como JSON de forma formatada."""
        if not filename.endswith(".json"):
            filename += ".json"
            
        filepath = os.path.join(path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return filepath

    def save_txt(self, path, filename, content):
        """Salva texto simples, útil para logs"""
        filepath = os.path.join(path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def save_human_readable_log(self, path, task, comments):
        """Cria e salva um arquivo de log fácil de ler em qualquer PC"""
        safe_name = self._sanitize_name(task.get('name', 'Sem_Nome'))
        task_id = task.get('id', 'sem_id')
        filename = f"[{task_id}] {safe_name} (RESUMO GERAL).txt"
        filepath = os.path.join(path, filename)
        
        # Limpar arquivo antigo se existir para evitar confusão no re-run
        old_file = os.path.join(path, "historico_completo.txt")
        if os.path.exists(old_file):
            try: os.remove(old_file)
            except: pass
            
        import datetime
        
        lines = []
        lines.append(f"📌 TAREFA: {task.get('name', 'Sem Nome')}")
        status = task.get("status", {}).get("status", "Desconhecido").upper()
        lines.append(f"📊 STATUS: {status}")
        
        creator = task.get("creator", {}).get("username", "Desconhecido")
        lines.append(f"👤 CRIADA POR: {creator}")
        
        assignees = [v.get("username", "") for v in task.get("assignees", [])]
        lines.append(f"👥 RESPONSÁVEIS: {', '.join(assignees) if assignees else 'Ninguém'}")
        
        sub_count = task.get('_local_subtasks_count', 0)
        lines.append(f"🌳 DEPENDENTES (Subtarefas atreladas): {sub_count}")
        
        custom_fields = task.get("custom_fields", [])
        if custom_fields:
            lines.append("\n📋 CAMPOS PERSONALIZADOS:")
            for cf in custom_fields:
                cf_name = cf.get("name", "Campo")
                cf_type = cf.get("type", "")
                cf_value = cf.get("value")
                if cf_value is None:
                    continue
                val_str = ""
                type_config = cf.get("type_config") or {}
                if cf_type == "drop_down" and isinstance(cf_value, int):
                    options = type_config.get("options", [])
                    for opt in options:
                        if opt.get("orderindex") == cf_value:
                            val_str = opt.get("name", "")
                            break
                elif cf_type == "labels" and isinstance(cf_value, list):
                    options = type_config.get("options", [])
                    label_names = [opt.get("label", "") for val_id in cf_value for opt in options if opt.get("id") == val_id]
                    val_str = ", ".join(label_names)
                elif cf_type == "currency":
                    val_str = f"${cf_value}"
                elif cf_type == "users" and isinstance(cf_value, list):
                    names = [u.get("username", "Sem Nome") for u in cf_value if isinstance(u, dict)]
                    val_str = ", ".join(names)
                elif cf_type == "date" and isinstance(cf_value, str):
                    try:
                        val_str = datetime.datetime.fromtimestamp(int(cf_value)/1000).strftime('%d/%m/%Y')
                    except: val_str = cf_value
                else:
                    val_str = str(cf_value)
                lines.append(f" - {cf_name}: {val_str}")

        lines.append("\n" + "="*60)
        lines.append(task.get("description") or "[Sem descrição atrelada a esta tarefa]")
        
        task_atts = task.get("attachments", [])
        if task_atts:
            lines.append("\n" + "="*60)
            lines.append(f"📦 ARQUIVOS GERAIS ANEXADOS NA TAREFA ({len(task_atts)})")
            lines.append("="*60)
            for att in task_atts:
                fname = att.get("title") or att.get("name") or "Arquivo Desconhecido"
                lines.append(f"📎 {fname} -> (Baixado para a pasta /Anexos)")
        
        lines.append("\n\n" + "="*60)
        lines.append(f"💬 HISTÓRICO DE COMENTÁRIOS E ANEXOS ({len(comments) if comments else 0})")
        lines.append("="*60)
        
        if comments:
            def _safe_date(c):
                d = c.get("date")
                if not d: return 0
                try: return int(d)
                except: return 0
                
            sorted_comments = sorted(comments, key=_safe_date)
            for c in sorted_comments:
                user = c.get("user", {}).get("username", "Desconhecido")
                
                try:
                    timestamp = _safe_date(c) / 1000
                    dt = datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M') if timestamp > 0 else "Data desconhecida"
                except:
                    dt = "Data desconhecida"
                
                text_content = c.get("comment_text") or c.get("text_content") or ""
                text_content = str(text_content).strip()
                lines.append(f"\n[{dt}] {user} comentou:")
                if text_content:
                    lines.append(f"  {text_content}")
                
                # Check for attachments inside comments
                for part in c.get("comment", []): 
                    if isinstance(part, dict) and part.get("type") == "attachment" and "attachment" in part:
                        att_name = part["attachment"].get("name", "Arquivo_Sem_Nome")
                        lines.append(f"  📎 [ANEXO ENVIADO NESTE COMENTÁRIO]: {att_name} (Enviado para a pasta /Anexos da tarefa)")
                        
                for root_att in c.get("attachments", []):
                    att_name = root_att.get("title") or root_att.get("name") or "Arquivo_Sem_Nome"
                    lines.append(f"  📎 [IMAGEM/ANEXO DETECTADO NESTE COMENTÁRIO]: {att_name} (Enviado para a pasta /Anexos)")
        else:
            lines.append("Nenhum comentário registrado nesta tarefa.")
            
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            print(f"      [Erro Log TXT] Falhou ao salvar TXT de {task.get('name')}: {e}")
            
        return filepath

    def save_human_readable_pdf(self, path, task, comments):
        """Cria e salva arquivo PDF bonitão com ReportLab contendo o descritivo geral"""
        safe_name = self._sanitize_name(task.get('name', 'Sem_Nome'))
        task_id = task.get('id', 'sem_id')
        filename = f"[{task_id}] {safe_name} (RESUMO GERAL).pdf"
        filepath = os.path.join(path, filename)
        
        old_file = os.path.join(path, "historico_completo.pdf")
        if os.path.exists(old_file):
            try: os.remove(old_file)
            except: pass
            
        try:
            doc = SimpleDocTemplate(filepath, pagesize=letter,
                                    rightMargin=40, leftMargin=40,
                                    topMargin=40, bottomMargin=18)
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(name='CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=12, textColor=colors.HexColor("#2C3E50")))
            styles.add(ParagraphStyle(name='CustomNormal', parent=styles['Normal'], fontSize=11, spaceAfter=6, textColor=colors.HexColor("#34495E")))
            styles.add(ParagraphStyle(name='CustomBold', parent=styles['Normal'], fontSize=11, spaceAfter=6, fontName='Helvetica-Bold', textColor=colors.HexColor("#2C3E50")))
            styles.add(ParagraphStyle(name='CommentHeader', parent=styles['Normal'], fontSize=10, spaceAfter=4, fontName='Helvetica-Bold', textColor=colors.HexColor("#2980B9")))
            styles.add(ParagraphStyle(name='CommentBody', parent=styles['Normal'], fontSize=11, spaceAfter=12, textColor=colors.HexColor("#2C3E50")))
            
            Story = []
            
            def escape_xml(text):
                if text is None: return ""
                text = str(text)
                # 1. Troca caracteres comuns que explodem a fonte Helvetica do ReportLab
                reps = {'•': '-', '–': '-', '—': '-', '“': '"', '”': '"', '‘': "'", '’': "'", '🚀': '[F]', '✅': '[V]', '❌': '[X]', '⚠️': '[!]'}
                for k, v in reps.items():
                    text = text.replace(k, v)
                
                # 2. Força remoção de emojis e unicode bizarro preservando PT-BR (Latin-1)
                text = text.encode('latin-1', errors='ignore').decode('latin-1')
                
                # 3. Fuga Padrão XML
                text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                # 4. Strip invisíveis de controle
                return ''.join(c for c in text if ord(c) >= 32 or c in '\n\r\t')
            
            def add_p_safe(text, style='CustomNormal'):
                text = escape_xml(text)
                text = text.replace('\n', '<br/>')
                Story.append(Paragraph(text, styles[style]))

            def add_p_raw(text, style='CustomNormal'):
                clean_text = ''.join(c for c in str(text) if ord(c) >= 32 or c in '\n\r\t')
                Story.append(Paragraph(clean_text, styles[style]))

            task_name = escape_xml(task.get('name', 'Sem Nome'))
            Story.append(Paragraph(f"TAREFA: {task_name}", styles['CustomTitle']))
            
            status = escape_xml(task.get("status", {}).get("status", "Desconhecido").upper())
            add_p_raw(f"<b>STATUS:</b> {status}", "CustomNormal")
            
            creator = escape_xml(task.get("creator", {}).get("username", "Desconhecido"))
            add_p_raw(f"<b>CRIADA POR:</b> {creator}", "CustomNormal")
            
            assignees_raw = [escape_xml(v.get("username", "")) for v in task.get("assignees", [])]
            add_p_raw(f"<b>RESPONSÁVEIS:</b> {', '.join(assignees_raw) if assignees_raw else 'Ninguém'}", "CustomNormal")
            
            sub_count = task.get('_local_subtasks_count', 0)
            add_p_raw(f"<b>DEPENDENTES (Subtarefas atreladas):</b> {sub_count}", "CustomNormal")
            
            # --- CUSTOM FIELDS ---
            custom_fields = task.get("custom_fields", [])
            if custom_fields:
                Story.append(Spacer(1, 10))
                add_p_raw("<b>CAMPOS PERSONALIZADOS:</b>", "CustomNormal")
                for cf in custom_fields:
                    cf_name = cf.get("name", "Campo").replace('<', '&lt;').replace('>', '&gt;')
                    cf_type = cf.get("type", "")
                    cf_value = cf.get("value")
                    
                    if cf_value is None:
                        continue
                        
                    val_str = ""
                    type_config = cf.get("type_config") or {}
                    if cf_type == "drop_down" and isinstance(cf_value, int):
                        options = type_config.get("options", [])
                        for opt in options:
                            if opt.get("orderindex") == cf_value:
                                val_str = opt.get("name", "")
                                break
                    elif cf_type == "labels" and isinstance(cf_value, list):
                        options = type_config.get("options", [])
                        label_names = [opt.get("label", "") for val_id in cf_value for opt in options if opt.get("id") == val_id]
                        val_str = ", ".join(label_names)
                    elif cf_type == "currency":
                        val_str = f"${cf_value}"
                    elif cf_type == "users" and isinstance(cf_value, list):
                        names = [u.get("username", "Sem Nome") for u in cf_value if isinstance(u, dict)]
                        val_str = ", ".join(names)
                    elif cf_type == "date" and isinstance(cf_value, str):
                        try:
                            import datetime
                            val_str = datetime.datetime.fromtimestamp(int(cf_value)/1000).strftime('%d/%m/%Y')
                        except: val_str = cf_value
                    else:
                        val_str = str(cf_value)
                        
                    cf_name = escape_xml(cf_name)
                    val_str = escape_xml(val_str)
                    add_p_raw(f" - <b>{cf_name}:</b> {val_str}", "CustomNormal")

            Story.append(Spacer(1, 15))
            Story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=15))
            
            # --- DESCRIÇÃO ---
            Story.append(Paragraph("DESCRIÇÃO DA TAREFA", styles['CustomBold']))
            desc = task.get("description") or "[Sem descrição atrelada a esta tarefa]"
            add_p_safe(desc, "CustomNormal")
            
            task_atts = task.get("attachments", [])
            if task_atts:
                Story.append(Spacer(1, 15))
                Story.append(Paragraph(f"ARQUIVOS GERAIS ANEXADOS NA TAREFA ({len(task_atts)})", styles['CustomBold']))
                for att in task_atts:
                    fname = escape_xml(att.get("title") or att.get("name") or "Arquivo_Desconhecido")
                    add_p_raw(f"📎 <b>{fname}</b> <i>(Imagem/Documento depositado físico na pasta /Anexos)</i>", "CustomNormal")
            
            Story.append(Spacer(1, 20))
            Story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=15))
            
            # --- COMENTÁRIOS ---
            Story.append(Paragraph(f"HISTÓRICO DE COMENTÁRIOS E ANEXOS ({len(comments) if comments else 0})", styles['CustomBold']))
            Story.append(Spacer(1, 10))
            
            if comments:
                def _safe_date(c):
                    d = c.get("date")
                    if not d: return 0
                    try: return int(d)
                    except: return 0
                    
                sorted_comments = sorted(comments, key=_safe_date)
                for c in sorted_comments:
                    user = escape_xml(c.get("user", {}).get("username", "Desconhecido"))
                    
                    try:
                        timestamp = _safe_date(c) / 1000
                        if timestamp > 0:
                            import datetime
                            dt = datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M')
                        else:
                            dt = "Data desconhecida"
                    except:
                        dt = "Data desconhecida"
                    
                    add_p_safe(f"[{dt}] {user} comentou:", "CommentHeader")
                    
                    text_content = c.get("comment_text") or c.get("text_content") or ""
                    text_content = str(text_content).strip()
                    if text_content:
                        add_p_safe(text_content, "CommentBody")
                    
                    for part in c.get("comment", []):
                        if isinstance(part, dict) and part.get("type") == "attachment" and "attachment" in part:
                            att_name = escape_xml(part["attachment"].get("name", "Arquivo_Sem_Nome"))
                            add_p_raw(f"📎 <i>[ANEXO NESTE COMENTÁRIO]: {att_name}</i>", "CommentBody")
                            
                    for root_att in c.get("attachments", []):
                        att_name = escape_xml(root_att.get("title") or root_att.get("name") or "Arquivo_Sem_Nome")
                        add_p_raw(f"📎 <i>[IMAGEM DETECTADA NESTE COMENTÁRIO]: {att_name}</i>", "CommentBody")
            else:
                add_p_safe("Nenhum comentário registrado nesta tarefa.")
                
            doc.build(Story)
        except Exception as e:
            print(f"      [Erro PDF] Não foi possível gerar PDF para {task.get('name', '')}. Motivo: {e}")
        return filepath
