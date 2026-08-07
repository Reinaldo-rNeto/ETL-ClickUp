import json
import os
import random
import string
import subprocess
import sys
import tempfile
import threading
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta

# ── Configuração SMTP fixa (interna ATI) ──────────────────────────────────────
_SMTP_HOST = "200.238.112.93"
_SMTP_PORTS = [25, 587, 465]  # Tenta cada porta até uma funcionar

CONFIG_FILE = "agendamento.json"
TASK_NAME = "ExtratorClickUp_ATI"

_DIAS_SEMANA_MAP = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}
_DIAS_SCHTASKS = {"seg": "MON", "ter": "TUE", "qua": "WED", "qui": "THU",
                  "sex": "FRI", "sab": "SAT", "dom": "SUN"}


def registrar_task_scheduler(cfg: dict, exe_path: str) -> tuple[bool, str]:
    """Registra a tarefa no Agendador de Tarefas do Windows."""
    try:
        iv_h = max(0, int(cfg.get("iv_horas", 1) or 0))
        iv_m = max(0, int(cfg.get("iv_minutos", 0) or 0))
        total_min = max(1, iv_h * 60 + iv_m)

        hora_inicio = cfg.get("hora_inicio", "08:00") or "08:00"
        try:
            datetime.strptime(hora_inicio, "%H:%M")
        except ValueError:
            hora_inicio = "08:00"

        dias_cfg = cfg.get("dias_semana", [])
        dias_sc = [_DIAS_SCHTASKS[d] for d in dias_cfg if d in _DIAS_SCHTASKS]

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE

        if dias_sc and total_min < 1440:
            # Ex: seg–sex, a cada 1h a partir de 08:00 → WEEKLY com /ri
            sc_args = [
                "/sc", "WEEKLY", "/mo", "1",
                "/d", ",".join(dias_sc),
                "/st", hora_inicio,
                "/ri", str(total_min),
            ]
        elif dias_sc:
            sc_args = ["/sc", "WEEKLY", "/mo", "1", "/d", ",".join(dias_sc), "/st", hora_inicio]
        else:
            sc_args = ["/sc", "MINUTE", "/mo", str(total_min), "/st", hora_inicio]

        cmd = ["schtasks", "/create", "/tn", TASK_NAME,
               "/tr", f'"{exe_path}" --agendado', "/f"] + sc_args

        result = subprocess.run(cmd, capture_output=True, text=True,
                                startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, "Tarefa registrada no Agendador de Tarefas do Windows."
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as e:
        return False, str(e)


def remover_task_scheduler() -> tuple[bool, str]:
    """Remove a tarefa do Agendador de Tarefas do Windows."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(
            ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
            capture_output=True, text=True,
            startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0, result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return False, str(e)

_PADRAO = {
    "ativo": False,
    "dias_semana": ["seg", "ter", "qua", "qui", "sex"],
    "hora_inicio": "08:00",
    "hora_fim": "19:00",
    "iv_horas": 1,
    "iv_minutos": 0,
    "ultima_execucao": "",
    "output_mode": "apenas_csv_api",
    "enviar_email": False,
    "remetente": "",
    "remetente_verificado": False,
    "destinatarios": "",
    "assunto": "Extrator ClickUp — Relatorio {data}",
    "space_ids": "",
    # Campos legados (mantidos para compatibilidade com configs antigas)
    "proxima_execucao": "",
    "iv_dias": 0, "iv_dias_ativo": False,
    "iv_horas_ativo": True, "iv_minutos_ativo": False,
}


def carregar() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return {**_PADRAO, **json.load(f)}
        except Exception:
            pass
    return dict(_PADRAO)


def salvar(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _enviar_via_powershell(remetente: str, destinatarios: list, assunto: str, corpo: str, anexos: list[str] | None = None) -> bool:
    """Envia email via PowerShell Send-MailMessage (processo do sistema, sem bloqueio de socket)."""
    dests = ",".join(f'"{d}"' for d in destinatarios)
    corpo_seg = corpo.replace("'", "`'").replace('"', '`"')
    assunto_seg = assunto.replace("'", "`'").replace('"', '`"')

    cmd_parts = [
        f"Send-MailMessage",
        f"-From '{remetente}'",
        f"-To {dests}",
        f"-Subject '{assunto_seg}'",
        f"-Body '{corpo_seg}'",
        f"-SmtpServer '{_SMTP_HOST}'",
        f"-Port {_SMTP_PORTS[0]}",
        f"-Encoding UTF8",
    ]
    if anexos:
        existentes = [a for a in anexos if a and os.path.exists(a)]
        if existentes:
            anexos_ps = ",".join(f"'{a}'" for a in existentes)
            cmd_parts.append(f"-Attachments {anexos_ps}")

    ps_cmd = " ".join(cmd_parts)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=30,
        startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode == 0:
        print("[SMTP] Email enviado via PowerShell.")
        return True
    print(f"[SMTP] PowerShell falhou: {result.stderr.strip()}")
    return False


def _conectar_smtp():
    """Tenta conectar ao relay SMTP nas portas disponíveis."""
    last_err = None
    for porta in _SMTP_PORTS:
        try:
            srv = smtplib.SMTP(_SMTP_HOST, porta, timeout=15)
            srv.ehlo()
            try:
                srv.starttls()
                srv.ehlo()
            except Exception:
                pass
            print(f"[SMTP] Conectado via smtplib porta {porta}")
            return srv
        except Exception as e:
            print(f"[SMTP] Porta {porta} falhou: {e}")
            last_err = e
    raise ConnectionError(f"Nenhuma porta disponível. Último erro: {last_err}")


class Agendador:
    """Verifica a cada 30 s se é hora de rodar a extração agendada."""

    def __init__(self, on_run=None, on_status=None):
        self.cfg = carregar()
        self._on_run = on_run        # callback(output_mode)
        self._on_status = on_status  # callback(texto)
        self._ativo = False
        self._thread = None
        self._codigo_pendente: dict = {}  # {email, codigo, ts}

    # ── Controle ──────────────────────────────────────────────────────────────

    def iniciar(self):
        if self._ativo:
            return
        self._ativo = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def parar(self):
        self._ativo = False

    def recarregar(self):
        self.cfg = carregar()
        self._notificar_status()

    # ── Loop principal ────────────────────────────────────────────────────────

    def _loop(self):
        while self._ativo:
            try:
                self._verificar()
            except Exception as e:
                print(f"[Agendador] Erro no loop: {e}")
            time.sleep(30)

    def _verificar(self):
        if not self.cfg.get("ativo"):
            return

        now = datetime.now()

        # Verifica dia da semana
        dias_cfg = self.cfg.get("dias_semana", [])
        if dias_cfg:
            dias_num = [_DIAS_SEMANA_MAP[d] for d in dias_cfg if d in _DIAS_SEMANA_MAP]
            if now.weekday() not in dias_num:
                return

        # Verifica janela de horário
        try:
            h_ini = datetime.strptime(self.cfg.get("hora_inicio", "00:00"), "%H:%M").time()
            h_fim = datetime.strptime(self.cfg.get("hora_fim", "23:59"), "%H:%M").time()
            if not (h_ini <= now.time() <= h_fim):
                return
        except ValueError:
            pass

        # Verifica intervalo desde a última execução
        iv_h = max(0, int(self.cfg.get("iv_horas", 1) or 0))
        iv_m = max(0, int(self.cfg.get("iv_minutos", 0) or 0))
        delta_min = iv_h * 60 + iv_m
        if delta_min < 1:
            delta_min = 60

        ultima_str = self.cfg.get("ultima_execucao", "")
        if ultima_str:
            try:
                dt_ultima = datetime.strptime(ultima_str, "%d/%m/%Y %H:%M")
                if (now - dt_ultima).total_seconds() < delta_min * 60:
                    return
            except ValueError:
                pass

        self.cfg["ultima_execucao"] = now.strftime("%d/%m/%Y %H:%M")
        salvar(self.cfg)
        self._notificar_status()

        print(f"\n[Agendador] Execucao automatica — {now.strftime('%d/%m/%Y %H:%M')}")
        if self._on_run:
            self._on_run(self.cfg.get("output_mode", "apenas_csv"))

    def _notificar_status(self):
        if not self._on_status:
            return
        if self.cfg.get("ativo"):
            dias = self.cfg.get("dias_semana", [])
            _NOMES = {"seg": "Seg", "ter": "Ter", "qua": "Qua", "qui": "Qui",
                      "sex": "Sex", "sab": "Sab", "dom": "Dom"}
            dias_str = "  ".join(_NOMES.get(d, d) for d in dias) if dias else "Todos os dias"
            iv_h = int(self.cfg.get("iv_horas", 0) or 0)
            iv_m = int(self.cfg.get("iv_minutos", 0) or 0)
            if iv_h and iv_m:
                iv_str = f"{iv_h}h {iv_m}min"
            elif iv_h:
                iv_str = f"{iv_h}h"
            else:
                iv_str = f"{iv_m}min"
            h_ini = self.cfg.get("hora_inicio", "08:00")
            h_fim = self.cfg.get("hora_fim", "19:00")
            ultima = self.cfg.get("ultima_execucao", "")
            msg = f"Agendado: {dias_str}   {h_ini}–{h_fim}   a cada {iv_str}"
            if ultima:
                msg += f"   Ultima: {ultima}"
            self._on_status(msg)
        else:
            self._on_status("Agendamento inativo")

    # ── Verificação de identidade por código ──────────────────────────────────

    def gerar_e_enviar_codigo(self, email: str) -> bool:
        """Gera código de 6 dígitos e envia para o email informado."""
        codigo = "".join(random.choices(string.digits, k=6))
        corpo = (
            f"Ola,\n\n"
            f"Seu codigo de verificacao para o Extrator ClickUp - ATI Pernambuco e:\n\n"
            f"    {codigo}\n\n"
            f"Valido por 10 minutos. Se voce nao solicitou isso, ignore este email.\n"
        )
        assunto = "Codigo de verificacao - Extrator ClickUp ATI"
        enviado = False

        # Tenta PowerShell primeiro (evita bloqueio de socket do exe)
        try:
            enviado = _enviar_via_powershell(email, [email], assunto, corpo)
        except Exception as e:
            print(f"[Verificacao] PowerShell falhou: {e}")

        # Fallback: smtplib direto
        if not enviado:
            try:
                msg = MIMEText(corpo, "plain", "utf-8")
                msg["From"] = email
                msg["To"] = email
                msg["Subject"] = assunto
                with _conectar_smtp() as srv:
                    srv.sendmail(email, [email], msg.as_bytes())
                enviado = True
            except Exception as e:
                print(f"[Verificacao] Falha ao enviar codigo: {e}")
                return False

        if enviado:
            self._codigo_pendente = {"email": email, "codigo": codigo, "ts": time.time()}
            print(f"[Verificacao] Codigo enviado para {email}")
        return enviado

    def verificar_codigo(self, email: str, codigo: str) -> bool:
        """Confirma o código digitado pelo usuário. Válido por 10 minutos."""
        p = self._codigo_pendente
        if not p:
            return False
        if p.get("email") != email.strip():
            return False
        if p.get("codigo") != codigo.strip():
            return False
        if time.time() - p.get("ts", 0) > 600:
            self._codigo_pendente = {}
            return False
        self._codigo_pendente = {}
        return True

    # ── Envio de e-mail ───────────────────────────────────────────────────────

    def enviar_email(self, arquivos: list[str] | None = None) -> bool:
        if not self.cfg.get("enviar_email", True):
            return True

        remetente = self.cfg.get("remetente", "").strip()
        destinatarios_str = self.cfg.get("destinatarios", "").strip()

        if not remetente or not destinatarios_str:
            print("[Email] Remetente ou destinatarios nao configurados.")
            return False

        if not self.cfg.get("remetente_verificado"):
            print("[Email] Remetente nao verificado. Email nao enviado.")
            return False

        destinatarios = [d.strip() for d in destinatarios_str.split(",") if d.strip()]
        anexos = [a for a in (arquivos or []) if a and os.path.exists(a)]
        try:
            assunto = self.cfg.get(
                "assunto", "Extrator ClickUp - Relatorio {data}"
            ).replace("{data}", datetime.now().strftime("%d/%m/%Y"))

            corpo = (
                "Prezados,\n\n"
                "Segue em anexo o relatorio gerado automaticamente pelo Extrator ClickUp - ATI Pernambuco.\n"
                f"Data/hora de geracao: {datetime.now().strftime('%d/%m/%Y as %H:%M')}\n\n"
                "Este e-mail foi enviado automaticamente. Nao responda a esta mensagem."
            )

            # Tenta PowerShell primeiro
            enviado = False
            try:
                enviado = _enviar_via_powershell(remetente, destinatarios, assunto, corpo, anexos)
            except Exception as e:
                print(f"[Email] PowerShell falhou: {e}")

            # Fallback: smtplib direto
            if not enviado:
                msg = MIMEMultipart()
                msg["From"] = remetente
                msg["To"] = ", ".join(destinatarios)
                msg["Subject"] = assunto
                msg.attach(MIMEText(corpo, "plain", "utf-8"))
                for caminho in anexos:
                    with open(caminho, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(caminho)}"')
                    msg.attach(part)
                with _conectar_smtp() as srv:
                    srv.sendmail(remetente, destinatarios, msg.as_bytes())
                enviado = True

            print(f"[Email] Enviado com sucesso para: {destinatarios_str}")
            return True
        except Exception as e:
            print(f"[Email] Falha ao enviar: {e}")
            return False
