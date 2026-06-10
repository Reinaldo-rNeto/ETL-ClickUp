import os
import requests
import string


class AttachmentDownloader:
    def __init__(self, headers=None):
        self.headers = headers if headers else {}

    def _make_att_entry(self, att, fallback_name="desconhecido"):
        """Cria o dict padronizado {id, name, url} a partir de um objeto de anexo."""
        base_name = att.get("title") or att.get("name") or fallback_name
        att_id = att.get("id", "semid")
        return {"id": att_id, "name": f"{att_id}_{base_name}", "url": att.get("url")}

    def _deep_find_attachment_urls(self, obj, found=None):
        """Varre recursivamente um objeto JSON em busca de URLs de anexos ClickUp."""
        if found is None:
            found = []
        if isinstance(obj, dict):
            if "url" in obj and isinstance(obj["url"], str) and "clickup-attachments.com" in obj["url"]:
                name = obj.get("title") or obj.get("name") or obj["url"].split("/")[-1].split("?")[0]
                if not name.lower().endswith(('.png', '.img', '.jpg', '.jpeg', '.gif', '.pdf', '.docx', '.csv', '.xlsx', '.mp4')):
                    name += ".png"
                att_id = obj.get("id", "deepid")
                found.append({"id": att_id, "name": f"{att_id}_{name}", "url": obj["url"]})
            for v in obj.values():
                self._deep_find_attachment_urls(v, found)
        elif isinstance(obj, list):
            for item in obj:
                self._deep_find_attachment_urls(item, found)
        return found

    def extract_attachments_from_task(self, task_data):
        return [self._make_att_entry(att) for att in task_data.get("attachments", [])]

    def extract_attachments_from_comments(self, comments_data):
        attachments = []
        seen_urls = set()

        for comment in comments_data:
            # Anexos no nível raiz do comentário
            for att in comment.get("attachments", []):
                entry = self._make_att_entry(att, "comentario_desc")
                if entry["url"] not in seen_urls:
                    seen_urls.add(entry["url"])
                    attachments.append(entry)

            # Deep scan em RichText (imagens inline e anexos escondidos)
            for entry in self._deep_find_attachment_urls(comment.get("comment", [])):
                if entry["url"] not in seen_urls:
                    seen_urls.add(entry["url"])
                    attachments.append(entry)

            # Anexos embedados via arrasto do ClickUp legado
            for part in comment.get("comment", []) if isinstance(comment.get("comment"), list) else []:
                if isinstance(part, dict) and part.get("type") == "attachment" and "attachment" in part:
                    entry = self._make_att_entry(part["attachment"], "embed_desc")
                    if entry["url"] not in seen_urls:
                        seen_urls.add(entry["url"])
                        attachments.append(entry)

        return attachments

    def download_attachment(self, url, filename, target_path):
        os.makedirs(target_path, exist_ok=True)

        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        safe_name = ''.join(c for c in filename if c in valid_chars).strip() or "anexo_sem_nome"

        if len(safe_name) > 60:
            name_part, ext_part = os.path.splitext(safe_name)
            safe_name = name_part[:50] + ("..." if len(name_part) > 50 else "") + ext_part

        filepath = os.path.join(target_path, safe_name)

        if os.path.exists(filepath):
            if safe_name.lower() in ["image.png", "edit.png"]:
                try: os.remove(filepath)
                except: pass
            else:
                return filepath

        try:
            response = requests.get(url, headers=self.headers, stream=True, timeout=20)

            # URL S3 auto-assinada: remove o header de autorização para evitar conflito de assinatura
            if response.status_code in [400, 401, 403]:
                response = requests.get(url, stream=True, timeout=20)

            response.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Corrige extensão via magic bytes (substitui imghdr descontinuado no Python 3.13+)
            try:
                with open(filepath, "rb") as bf:
                    head = bf.read(32)
                real_type = None
                if head.startswith(b"\xff\xd8\xff"):
                    real_type = "jpeg"
                elif head.startswith(b"\x89PNG\r\n\x1a\n"):
                    real_type = "png"
                elif head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
                    real_type = "gif"
                elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                    real_type = "webp"

                if real_type:
                    real_ext = '.jpg' if real_type == 'jpeg' else f".{real_type}"
                    if not filepath.lower().endswith(real_ext):
                        nova_path = os.path.splitext(filepath)[0] + real_ext
                        if os.path.exists(nova_path):
                            os.remove(nova_path)
                        os.rename(filepath, nova_path)
                        return nova_path
            except Exception:
                pass

            return filepath
        except Exception as e:
            print(f"Erro ao baixar anexo '{filename}' do link {url}: {e}")
            return None
