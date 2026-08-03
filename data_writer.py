import os
import json
import sys
import datetime
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors
    _REPORTLAB_OK = True
except ImportError:
    _REPORTLAB_OK = False


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
        # Windows MAX_PATH bypass: prefixo \\?\ permite caminhos acima de 260 caracteres
        if os.name == 'nt' and not self.base_dir.startswith('\\\\?\\'):
            self.base_dir = '\\\\?\\' + self.base_dir

        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def _sanitize_name(self, name, max_len=65):
        """Retorna nome seguro para uso como pasta/arquivo no Windows."""
        if not name:
            return "Sem_Nome"
        for char in '<>:"/\\|?*\n\r\t':
            name = name.replace(char, "_")
        name = name.strip()
        if len(name) > max_len:
            name = name[:max_len].strip() + "_"
        while name.endswith('.'):
            name = name[:-1]
        return name.strip() or "Sem_Nome_Valido"

    def _format_custom_field(self, cf):
        """Converte um custom field do ClickUp em string legível. Retorna None se sem valor."""
        cf_value = cf.get("value")
        if cf_value is None:
            return None
        cf_type = cf.get("type", "")
        type_config = cf.get("type_config") or {}
        if cf_type == "drop_down" and isinstance(cf_value, int):
            for opt in type_config.get("options", []):
                if opt.get("orderindex") == cf_value:
                    return opt.get("name", "")
            return ""
        if cf_type == "labels" and isinstance(cf_value, list):
            options = type_config.get("options", [])
            return ", ".join(
                opt.get("label", "") for val_id in cf_value for opt in options if opt.get("id") == val_id
            )
        if cf_type == "currency":
            return f"${cf_value}"
        if cf_type == "users" and isinstance(cf_value, list):
            return ", ".join(u.get("username", "Sem Nome") for u in cf_value if isinstance(u, dict))
        if cf_type == "date" and isinstance(cf_value, str):
            try:
                return datetime.datetime.fromtimestamp(int(cf_value) / 1000).strftime('%d/%m/%Y')
            except Exception:
                return str(cf_value)
        return str(cf_value)

    def _safe_comment_date(self, comment):
        """Retorna o timestamp inteiro do comentário, ou 0 se ausente/inválido."""
        d = comment.get("date")
        if not d:
            return 0
        try:
            return int(d)
        except Exception:
            return 0

    def create_hierarchy(self, space_name, folder_name=None, list_name=None,
                          task_id=None, task_name=None, parent_id=None,
                          parent_name=None, parent_chain=None):
        path = os.path.join(self.base_dir, self._sanitize_name(space_name))

        if folder_name:
            path = os.path.join(path, self._sanitize_name(folder_name))
        else:
            path = os.path.join(path, "Listas_Sem_Pasta")

        if list_name:
            path = os.path.join(path, self._sanitize_name(list_name))

        if parent_chain:
            for p_id, p_name in parent_chain:
                path = os.path.join(path, f"[{p_id}] {self._sanitize_name(p_name or 'Tarefa_Pai')}", "Subtarefas")
        elif parent_id:
            path = os.path.join(path, f"[{parent_id}] {self._sanitize_name(parent_name or 'Tarefa_Pai')}", "Subtarefas")

        if task_id and task_name:
            path = os.path.join(path, f"[{task_id}] {self._sanitize_name(task_name)}")

        os.makedirs(path, exist_ok=True)
        return path

    def save_json(self, path, filename, data):
        if not filename.endswith(".json"):
            filename += ".json"
        filepath = os.path.join(path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return filepath

    def save_txt(self, path, filename, content):
        filepath = os.path.join(path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def save_human_readable_log(self, path, task, comments):
        safe_name = self._sanitize_name(task.get('name', 'Sem_Nome'))
        task_id = task.get('id', 'sem_id')
        filename = f"[{task_id}] {safe_name} (RESUMO GERAL).txt"
        filepath = os.path.join(path, filename)

        old_file = os.path.join(path, "historico_completo.txt")
        if os.path.exists(old_file):
            try: os.remove(old_file)
            except: pass

        lines = []
        lines.append(f"📌 TAREFA: {task.get('name', 'Sem Nome')}")
        lines.append(f"📊 STATUS: {task.get('status', {}).get('status', 'Desconhecido').upper()}")
        lines.append(f"👤 CRIADA POR: {task.get('creator', {}).get('username', 'Desconhecido')}")

        assignees = [v.get("username", "") for v in task.get("assignees", [])]
        lines.append(f"👥 RESPONSÁVEIS: {', '.join(assignees) if assignees else 'Ninguém'}")
        lines.append(f"🌳 DEPENDENTES (Subtarefas atreladas): {task.get('_local_subtasks_count', 0)}")

        custom_fields = task.get("custom_fields", [])
        if custom_fields:
            lines.append("\n📋 CAMPOS PERSONALIZADOS:")
            for cf in custom_fields:
                val_str = self._format_custom_field(cf)
                if val_str is not None:
                    lines.append(f" - {cf.get('name', 'Campo')}: {val_str}")

        lines.append("\n" + "=" * 60)
        lines.append(task.get("description") or "[Sem descrição atrelada a esta tarefa]")

        task_atts = task.get("attachments", [])
        if task_atts:
            lines.append("\n" + "=" * 60)
            lines.append(f"📦 ARQUIVOS GERAIS ANEXADOS NA TAREFA ({len(task_atts)})")
            lines.append("=" * 60)
            for att in task_atts:
                fname = att.get("title") or att.get("name") or "Arquivo Desconhecido"
                lines.append(f"📎 {fname} -> (Baixado para a pasta /Anexos)")

        lines.append("\n\n" + "=" * 60)
        lines.append(f"💬 HISTÓRICO DE COMENTÁRIOS E ANEXOS ({len(comments) if comments else 0})")
        lines.append("=" * 60)

        if comments:
            for c in sorted(comments, key=self._safe_comment_date):
                user = c.get("user", {}).get("username", "Desconhecido")
                ts = self._safe_comment_date(c) / 1000
                dt = datetime.datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M') if ts > 0 else "Data desconhecida"
                text_content = str(c.get("comment_text") or c.get("text_content") or "").strip()
                lines.append(f"\n[{dt}] {user} comentou:")
                if text_content:
                    lines.append(f"  {text_content}")
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
        safe_name = self._sanitize_name(task.get('name', 'Sem_Nome'))
        task_id = task.get('id', 'sem_id')
        filename = f"[{task_id}] {safe_name} (RESUMO GERAL).pdf"
        filepath = os.path.join(path, filename)

        old_file = os.path.join(path, "historico_completo.pdf")
        if os.path.exists(old_file):
            try: os.remove(old_file)
            except: pass

        if not _REPORTLAB_OK:
            return

        try:
            doc = SimpleDocTemplate(filepath, pagesize=letter,
                                     rightMargin=40, leftMargin=40,
                                     topMargin=40, bottomMargin=18)
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(name='CustomTitle', parent=styles['Heading1'],
                                       fontSize=16, spaceAfter=12, textColor=colors.HexColor("#2C3E50")))
            styles.add(ParagraphStyle(name='CustomNormal', parent=styles['Normal'],
                                       fontSize=11, spaceAfter=6, textColor=colors.HexColor("#34495E")))
            styles.add(ParagraphStyle(name='CustomBold', parent=styles['Normal'],
                                       fontSize=11, spaceAfter=6, fontName='Helvetica-Bold',
                                       textColor=colors.HexColor("#2C3E50")))
            styles.add(ParagraphStyle(name='CommentHeader', parent=styles['Normal'],
                                       fontSize=10, spaceAfter=4, fontName='Helvetica-Bold',
                                       textColor=colors.HexColor("#2980B9")))
            styles.add(ParagraphStyle(name='CommentBody', parent=styles['Normal'],
                                       fontSize=11, spaceAfter=12, textColor=colors.HexColor("#2C3E50")))

            Story = []

            def escape_xml(text):
                if text is None: return ""
                text = str(text)
                for k, v in {'•': '-', '–': '-', '—': '-', '"': '"', '"': '"',
                              ''': "'", ''': "'", '🚀': '[F]', '✅': '[V]',
                              '❌': '[X]', '⚠️': '[!]'}.items():
                    text = text.replace(k, v)
                text = text.encode('latin-1', errors='ignore').decode('latin-1')
                text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                return ''.join(c for c in text if ord(c) >= 32 or c in '\n\r\t')

            def add_p_safe(text, style='CustomNormal'):
                Story.append(Paragraph(escape_xml(text).replace('\n', '<br/>'), styles[style]))

            def add_p_raw(text, style='CustomNormal'):
                clean = ''.join(c for c in str(text) if ord(c) >= 32 or c in '\n\r\t')
                Story.append(Paragraph(clean, styles[style]))

            Story.append(Paragraph(f"TAREFA: {escape_xml(task.get('name', 'Sem Nome'))}", styles['CustomTitle']))
            add_p_raw(f"<b>STATUS:</b> {escape_xml(task.get('status', {}).get('status', 'Desconhecido').upper())}", "CustomNormal")
            add_p_raw(f"<b>CRIADA POR:</b> {escape_xml(task.get('creator', {}).get('username', 'Desconhecido'))}", "CustomNormal")

            assignees_raw = [escape_xml(v.get("username", "")) for v in task.get("assignees", [])]
            add_p_raw(f"<b>RESPONSÁVEIS:</b> {', '.join(assignees_raw) if assignees_raw else 'Ninguém'}", "CustomNormal")
            add_p_raw(f"<b>DEPENDENTES (Subtarefas atreladas):</b> {task.get('_local_subtasks_count', 0)}", "CustomNormal")

            custom_fields = task.get("custom_fields", [])
            if custom_fields:
                Story.append(Spacer(1, 10))
                add_p_raw("<b>CAMPOS PERSONALIZADOS:</b>", "CustomNormal")
                for cf in custom_fields:
                    val_str = self._format_custom_field(cf)
                    if val_str is not None:
                        cf_name = escape_xml(cf.get("name", "Campo"))
                        add_p_raw(f" - <b>{cf_name}:</b> {escape_xml(val_str)}", "CustomNormal")

            Story.append(Spacer(1, 15))
            Story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=15))

            Story.append(Paragraph("DESCRIÇÃO DA TAREFA", styles['CustomBold']))
            add_p_safe(task.get("description") or "[Sem descrição atrelada a esta tarefa]", "CustomNormal")

            task_atts = task.get("attachments", [])
            if task_atts:
                Story.append(Spacer(1, 15))
                Story.append(Paragraph(f"ARQUIVOS GERAIS ANEXADOS NA TAREFA ({len(task_atts)})", styles['CustomBold']))
                for att in task_atts:
                    fname = escape_xml(att.get("title") or att.get("name") or "Arquivo_Desconhecido")
                    add_p_raw(f"📎 <b>{fname}</b> <i>(Imagem/Documento depositado físico na pasta /Anexos)</i>", "CustomNormal")

            Story.append(Spacer(1, 20))
            Story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=15))
            Story.append(Paragraph(f"HISTÓRICO DE COMENTÁRIOS E ANEXOS ({len(comments) if comments else 0})", styles['CustomBold']))
            Story.append(Spacer(1, 10))

            if comments:
                for c in sorted(comments, key=self._safe_comment_date):
                    user = escape_xml(c.get("user", {}).get("username", "Desconhecido"))
                    ts = self._safe_comment_date(c) / 1000
                    dt = datetime.datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M') if ts > 0 else "Data desconhecida"
                    add_p_safe(f"[{dt}] {user} comentou:", "CommentHeader")

                    text_content = str(c.get("comment_text") or c.get("text_content") or "").strip()
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
