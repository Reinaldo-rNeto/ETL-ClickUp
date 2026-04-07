import os
import requests
import string

class AttachmentDownloader:
    def __init__(self, headers=None):
        # A própria API do ClickUp usa os headers com Token para dar acesso aos anexos
        self.headers = headers if headers else {}

    def extract_attachments_from_task(self, task_data):
        """Retorna uma lista de URLs e Nomes dos anexos de uma tarefa"""
        attachments = []
        if "attachments" in task_data:
            for att in task_data["attachments"]:
                base_name = att.get("title") or att.get("name") or "desconhecido"
                att_id = att.get("id", "semid")
                attachments.append({
                    "id": att_id,
                    "name": f"{att_id}_{base_name}",
                    "url": att.get("url")
                })
        return attachments

    def extract_attachments_from_comments(self, comments_data):
        """Varre comentários e retorna a lista de todos os arquivos anexados"""
        attachments = []
        for comment in comments_data:
            # 1. Puxa os prints e arquivos atrelados diretamente no nível raiz do comentário
            if "attachments" in comment:
                for att in comment["attachments"]:
                    base_name = att.get("title") or att.get("name") or "comentario_desc"
                    att_id = att.get("id", "semid")
                    attachments.append({
                        "id": att_id,
                        "name": f"{att_id}_{base_name}",
                        "url": att.get("url")
                    })
                    
            # Deep Scan Forçar Bruta para imagens escondidas no RichText de empresas (V8.13)
            def _deep_find_urls(obj):
                found = []
                if isinstance(obj, dict):
                    if "url" in obj and isinstance(obj["url"], str) and "clickup-attachments.com" in obj["url"]:
                        name = obj.get("title") or obj.get("name") or obj["url"].split("/")[-1].split("?")[0]
                        if not name.lower().endswith(('.png', '.img', '.jpg', '.jpeg', '.gif', '.pdf', '.docx', '.csv', '.xlsx', '.mp4')):
                           name += ".png" # Forçar formato base se vier obscuro
                        att_id = obj.get("id", "deepid")
                        found.append({"id": att_id, "name": f"{att_id}_{name}", "url": obj["url"]})
                    for k, v in obj.items():
                        found.extend(_deep_find_urls(v))
                elif isinstance(obj, list):
                    for item in obj:
                        found.extend(_deep_find_urls(item))
                return found
                
            deep_atts = _deep_find_urls(comment.get("comment", []))
            for da in deep_atts:
                if da["url"] not in [a["url"] for a in attachments]:
                    attachments.append(da)
                    
            # 2. Puxa prints que estejam embedados isoladamente via arrasto do ClickUp antigo
            if "comment" in comment and isinstance(comment["comment"], list):
                for part in comment["comment"]:
                    if isinstance(part, dict) and part.get("type") == "attachment" and "attachment" in part:
                        att = part["attachment"]
                        base_name = att.get("title") or att.get("name") or "embed_desc"
                        att_id = att.get("id", "semid")
                        attachments.append({
                            "id": att_id,
                            "name": f"{att_id}_{base_name}",
                            "url": att.get("url")
                        })
        return attachments

    def download_attachment(self, url, filename, target_path):
        """Baixa o arquivo em bytes de um URL e salva no caminho fornecido."""
        os.makedirs(target_path, exist_ok=True)

        # Sanitize filename for safe file system use
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        safe_name = ''.join(c for c in filename if c in valid_chars)
        safe_name = safe_name.strip()
        if not safe_name:
            safe_name = "anexo_sem_nome"
            
        # Corte brutal caso o nome do PDF/Imagem seja bizarramente grande
        if len(safe_name) > 60:
            name_part, ext_part = os.path.splitext(safe_name)
            # Ensure name_part is not too short after truncation to avoid "..." at the beginning
            truncated_name_part = name_part[:50]
            if len(name_part) > 50:
                safe_name = truncated_name_part + "..." + ext_part
            else:
                safe_name = name_part + ext_part # No truncation needed if name_part is already short

        filepath = os.path.join(target_path, safe_name)
        
        # Ignora se já tivermos extraído (Resume extrações interrompidas),
        # EXCETO caches genéricos suspeitos do ClickUp ('image.png') velhos.
        if os.path.exists(filepath):
            if safe_name.lower() in ["image.png", "edit.png"]:
                try: os.remove(filepath)
                except: pass
            else:
                return filepath
            
        try:
            # 1. Tenta baixar normalmente injetando o Token da API ClickUp
            response = requests.get(url, headers=self.headers, stream=True, timeout=20)
            
            # 2. Se a Amazon S3/GCP que guarda os anexos cuspir Erro 403/400 (Signature Does Not Match),
            # significa que a URL já está auto-assinada e a injeção do cabeçalho corrompeu ela. 
            # Reverte pra request anônimo puro.
            if response.status_code in [400, 401, 403]:
                # Tenta baixar cruamente sem Authorization caso S3 ja possua assinatura na URL
                response = requests.get(url, stream=True, timeout=20)
                
            response.raise_for_status()
            
            # Reconstruct clean path
            file_path = os.path.join(target_path, safe_name)
            
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # 3. Inspeção Binária Infalível Pós-Download
            # Substituição do imghdr descontinuado no Python 3.13+ analisando Magic Bytes
            try:
                real_type = None
                with open(file_path, "rb") as bf:
                    head = bf.read(32)
                    if head.startswith(b"\xff\xd8\xff"):
                        real_type = "jpeg"
                    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
                        real_type = "png"
                    elif head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
                        real_type = "gif"
                    elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                        real_type = "webp"
                        
                if real_type:
                    if real_type == 'jpeg': real_ext = '.jpg'
                    else: real_ext = f".{real_type}"
                    
                    # Se ele veio corrompido como a extensao errada
                    if not file_path.lower().endswith(real_ext):
                        nova_file_path = os.path.splitext(file_path)[0] + real_ext
                        # Deleta se a correta existir no mesmo lugar para evitar file exists error
                        if os.path.exists(nova_file_path):
                            os.remove(nova_file_path)
                        os.rename(file_path, nova_file_path)
                        return nova_file_path
            except: pass
            
            return file_path
        except Exception as e:
            print(f"Erro ao baixar anexo '{filename}' do link {url}: {e}")
            return None
