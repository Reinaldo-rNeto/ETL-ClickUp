import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import sys
import os
import time
from dotenv import load_dotenv

import main as core_main
from agendador import Agendador, carregar as _sch_load, salvar as _sch_save, registrar_task_scheduler, remover_task_scheduler

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# Paleta
BG      = "#F7F8FA"
WHITE   = "#FFFFFF"
GRAY_L  = "#F3F4F6"
BORDER  = "#E5E7EB"
T1      = "#111827"
T2      = "#6B7280"
T3      = "#9CA3AF"
BLUE    = "#2563EB"
BLUE_H  = "#1D4ED8"
GREEN   = "#16A34A"
GREEN_H = "#15803D"
AMBER   = "#D97706"
AMBER_H = "#B45309"
HDR     = "#1E293B"
LOG_BG  = "#0F172A"
LOG_T   = "#CBD5E1"


class StdoutRedirector:
    def __init__(self, widget, app):
        self.widget = widget
        self.app = app

    def write(self, text):
        self.app.after(0, self._write, text)

    def _write(self, text):
        self.widget.insert("end", text)
        self.widget.see("end")
        # Atualiza o card de status com progresso do Playwright em tempo real
        t = text.strip()
        try:
            if "[PW] -- Exportando:" in t:
                parte = t.split("Exportando:")[1].strip(" -")
                self.app._lbl_desc.configure(text=f"Exportando: {parte}")
            elif "[PW] XLSX salvo:" in t or "[PW] CSV salvo:" in t:
                tipo = "XLSX" if "XLSX" in t else "CSV"
                self.app._lbl_desc.configure(text=f"Arquivo {tipo} salvo.")
            elif "[PW] OK —" in t or "[PW] OK -" in t or "OK — 2 arquivo" in t:
                self.app._lbl_desc.configure(text="Espaco concluido. Aguardando proximo...")
            elif "[PW] ERRO:" in t:
                resumo = t.replace("[PW] ERRO:", "").strip()[:90]
                self.app._lbl_desc.configure(text=f"Aviso: {resumo}")
            elif "EXPORTACAO NATIVA CONCLUIDA" in t:
                self.app._lbl_desc.configure(text="Exportacao nativa concluida com sucesso!")
            elif "Playwright nao baixou" in t or "Exportacao nativa falhou" in t:
                self.app._lbl_desc.configure(text="Playwright indisponivel — usando extracao via API...")
        except Exception:
            pass

    def flush(self): pass


class ExtratorApp(ctk.CTk):

    # (titulo, descricao, valor)
    _MODOS = [
        (
            "Relatorio completo",
            "PDF por tarefa  +  JSON  +  Anexos baixados  +  Planilha Excel",
            "completo",
        ),
        (
            "Dados e planilha",
            "JSON de todas as tarefas  +  Planilha Excel   sem baixar arquivos",
            "csv_json",
        ),
        (
            "Exportacao nativa  (Playwright)",
            "Baixa XLSX + CSV direto do ClickUp via navegador   salvo em Dados_BI_ClickUp/Playwright/   requer email/senha no .env",
            "apenas_csv",
        ),
        (
            "Consolidado via API",
            "Extrai via API e gera planilha Excel consolidada com todos os espacos   salvo em Dados_BI_ClickUp/API/",
            "apenas_csv_api",
        ),
    ]

    def __init__(self):
        super().__init__()
        self.title("Extrator ClickUp — ATI Pernambuco")
        self.geometry("1200x700")
        self.minsize(1000, 620)
        self.configure(fg_color=BG)

        self.ws_map: dict = {}
        self._space_map: dict = {}          # nome → space_id
        self.space_vars: dict = {}          # nome → BooleanVar
        self._token_value: str = ""
        self._running: bool = False
        self._start_time: float | None = None
        self._timer_job = None
        self._mode_var = ctk.StringVar(value="completo")

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()

        sys.stdout = StdoutRedirector(self.txt_log, self)
        sys.stderr = sys.stdout

        # Agendador — inicia loop em background
        self._agendador = Agendador(
            on_run=self._executar_agendado,
            on_status=self._atualizar_label_agendamento,
        )
        self._agendador.iniciar()

        self.pre_load_env()
        self._atualizar_label_agendamento()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, height=56, fg_color=HDR, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        # Marca
        marca = ctk.CTkFrame(hdr, fg_color="transparent")
        marca.grid(row=0, column=0, padx=22, sticky="w")
        ctk.CTkLabel(marca, text="ATI",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#64748B").pack(side="left")
        ctk.CTkLabel(marca, text="  /  ",
                     font=ctk.CTkFont(size=13), text_color="#334155").pack(side="left")
        ctk.CTkLabel(marca, text="Extrator ClickUp",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#F1F5F9").pack(side="left")

        # Botão de configuração do token
        self.btn_token_cfg = ctk.CTkButton(
            hdr, text="Chave de Acesso",
            height=30, corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color="#334155", hover_color="#475569",
            text_color="#CBD5E1",
            command=self._abrir_dialogo_token,
        )
        self.btn_token_cfg.grid(row=0, column=1, padx=(0, 10), sticky="e")

        # Badge de status de conexão
        self._badge = ctk.CTkFrame(hdr, fg_color="#334155", corner_radius=20)
        self._badge.grid(row=0, column=2, padx=(0, 22), sticky="e")
        self._badge_lbl = ctk.CTkLabel(
            self._badge, text="Nao conectado",
            font=ctk.CTkFont(size=11), text_color="#94A3B8",
        )
        self._badge_lbl.pack(padx=14, pady=5)

    def _set_badge(self, texto, cor_fundo="#334155", cor_texto="#94A3B8"):
        def _do():
            self._badge.configure(fg_color=cor_fundo)
            self._badge_lbl.configure(text=texto, text_color=cor_texto)
        self.after(0, _do)

    def _abrir_dialogo_token(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Chave de Acesso ClickUp")
        dlg.geometry("480x230")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        # ── Token ────────────────────────────────────────────────────────────
        ctk.CTkLabel(dlg, text="Token de API",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=T1).pack(padx=28, pady=(28, 2), anchor="w")
        ctk.CTkLabel(dlg,
                     text="Encontre em: ClickUp → seu avatar → Aplicativos → API Token",
                     font=ctk.CTkFont(size=11), text_color=T2).pack(padx=28, anchor="w")

        entry = ctk.CTkEntry(
            dlg, show="*", height=38, corner_radius=6,
            fg_color=GRAY_L, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text_color=T3,
            font=ctk.CTkFont(size=12, family="Consolas"),
        )
        entry.pack(fill="x", padx=28, pady=(12, 0))
        if self._token_value:
            entry.insert(0, self._token_value)

        def confirmar():
            tok = entry.get().strip()
            if not tok:
                return
            self._token_value = tok
            os.environ["CLICKUP_API_TOKEN"] = tok
            dlg.destroy()
            self.conectar()

        ctk.CTkButton(
            dlg, text="Salvar e Conectar", height=38, corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=BLUE, hover_color=BLUE_H, text_color=WHITE,
            command=confirmar,
        ).pack(fill="x", padx=28, pady=18)

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")

        # Painel arrastável — divisor deslizante entre config e atividade
        paned = tk.PanedWindow(
            body,
            orient=tk.HORIZONTAL,
            bg="#C1C9D4",      # cor do divisor
            sashwidth=5,
            sashpad=0,
            sashrelief=tk.FLAT,
            relief=tk.FLAT,
            bd=0,
        )
        paned.pack(fill="both", expand=True)

        left_pane = ctk.CTkFrame(paned, fg_color=WHITE, corner_radius=0)
        right_pane = ctk.CTkFrame(paned, fg_color=BG, corner_radius=0)

        paned.add(left_pane, minsize=280, width=368, stretch="always")
        paned.add(right_pane, minsize=360, stretch="always")

        self._paned = paned
        self._build_painel_config(left_pane)
        self._build_painel_atividade(right_pane)

        # Reposiciona o sash proporcionalmente sempre que a janela redimensionar
        def _ajustar_sash(event):
            if event.widget is not self:
                return
            pos = max(280, min(int(event.width * 0.36), 540))
            try:
                self._paned.sash_place(0, pos, 0)
            except Exception:
                pass
        self.bind("<Configure>", _ajustar_sash)
        # Posição inicial após render completo
        self.after(150, lambda: self._paned.sash_place(
            0, max(280, int(self.winfo_width() * 0.36)), 0))

    # ── Painel esquerdo: Configuração ─────────────────────────────────────────

    def _build_painel_config(self, parent):
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=WHITE, corner_radius=0,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color="#D1D5DB",
        )
        scroll.pack(fill="both", expand=True)

        c = scroll  # alias para o container

        # --- Seleção de Espaços (Portfólios) ---
        self._rotulo(c, "Portfólios / Espaços")

        sel_row = ctk.CTkFrame(c, fg_color=WHITE)
        sel_row.pack(fill="x", padx=24, pady=(6, 0))
        ctk.CTkButton(
            sel_row, text="Selecionar todos", width=130, height=28, corner_radius=5,
            font=ctk.CTkFont(size=11), fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER, text_color=T2,
            command=lambda: [v.set(True) for v in self.space_vars.values()],
        ).pack(side="left")
        ctk.CTkButton(
            sel_row, text="Limpar", width=70, height=28, corner_radius=5,
            font=ctk.CTkFont(size=11), fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER, text_color=T2,
            command=lambda: [v.set(False) for v in self.space_vars.values()],
        ).pack(side="left", padx=(8, 0))

        self._space_check_frame = ctk.CTkFrame(c, fg_color=GRAY_L, corner_radius=8)
        self._space_check_frame.pack(fill="x", padx=24, pady=(8, 0))

        self._space_placeholder = ctk.CTkLabel(
            self._space_check_frame,
            text="Conecte para ver os espaços disponíveis",
            font=ctk.CTkFont(size=11), text_color=T3,
        )
        self._space_placeholder.pack(pady=14)

        self._divisor(c)

        # --- Modo de exportação (radio com descrição) ---
        self._rotulo(c, "O que deseja exportar?")

        self._modo_desc_labels: list[ctk.CTkLabel] = []
        for titulo, descricao, valor in self._MODOS:
            bloco = ctk.CTkFrame(c, fg_color=WHITE)
            bloco.pack(fill="x", padx=24, pady=(10, 0))

            ctk.CTkRadioButton(
                bloco, text=titulo, value=valor,
                variable=self._mode_var,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=T1,
                fg_color=BLUE, hover_color=BLUE_H,
                border_width_unchecked=2, border_width_checked=6,
            ).pack(anchor="w")

            lbl_desc = ctk.CTkLabel(
                bloco, text=descricao,
                font=ctk.CTkFont(size=10), text_color=T3,
                justify="left", anchor="w", wraplength=280,
            )
            lbl_desc.pack(anchor="w", fill="x", padx=24, pady=(2, 0))
            self._modo_desc_labels.append(lbl_desc)

        # Atualiza wraplength quando o painel esquerdo redimensiona
        def _on_left_resize(event):
            if event.widget is not parent:
                return
            wrap = max(100, event.width - 64)
            for lbl in self._modo_desc_labels:
                lbl.configure(wraplength=wrap)
        parent.bind("<Configure>", _on_left_resize)

        self._divisor(c)

        # --- Filtros opcionais ---
        self._rotulo(c, "Filtros   (opcional)")

        ctk.CTkLabel(c, text="Status das tarefas",
                     font=ctk.CTkFont(size=11), text_color=T2).pack(
            padx=24, pady=(10, 2), anchor="w"
        )
        self.cmb_status = ctk.CTkOptionMenu(
            c, values=["Todas", "Somente Abertas", "Somente Fechadas"],
            dynamic_resizing=False, height=34, corner_radius=6,
            fg_color=GRAY_L, button_color="#D1D5DB",
            button_hover_color=T3, text_color=T1,
            font=ctk.CTkFont(size=12),
        )
        self.cmb_status.pack(fill="x", padx=24)
        self.cmb_status.set("Todas")

        ctk.CTkLabel(c, text="Busca por nome de lista",
                     font=ctk.CTkFont(size=11), text_color=T2).pack(
            padx=24, pady=(12, 2), anchor="w"
        )
        self.entry_sprint = ctk.CTkEntry(
            c, placeholder_text="Ex: Sprint 2",
            height=34, corner_radius=6,
            fg_color=GRAY_L, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text_color=T3,
            font=ctk.CTkFont(size=12),
        )
        self.entry_sprint.pack(fill="x", padx=24)

        # Filtro de data
        data_box = ctk.CTkFrame(c, fg_color=WHITE)
        data_box.pack(fill="x", padx=24, pady=(12, 0))

        self.chk_date_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            data_box, text="Data minima de atualizacao",
            variable=self.chk_date_var, command=self.toggle_date,
            font=ctk.CTkFont(size=11), text_color=T2,
            fg_color=BLUE, hover_color=BLUE_H,
            checkmark_color=WHITE, corner_radius=4,
        ).pack(anchor="w")

        try:
            from tkcalendar import DateEntry
            self.entry_date = DateEntry(
                data_box, width=14,
                background="#1E293B", foreground="white",
                borderwidth=1, date_pattern="dd/mm/yyyy",
                state="disabled", font=("Segoe UI", 10),
            )
            self.entry_date.pack(anchor="w", pady=(6, 0))
            self.entry_date.delete(0, "end")
        except ImportError:
            self.entry_date = ctk.CTkEntry(
                data_box, width=130, placeholder_text="DD/MM/AAAA",
                height=32, corner_radius=6,
                fg_color=GRAY_L, border_color=BORDER, border_width=1,
                text_color=T1, placeholder_text_color=T3,
                font=ctk.CTkFont(size=12),
            )
            self.entry_date.pack(anchor="w", pady=(6, 0))
            self.entry_date.configure(state="disabled")

        self._divisor(c)

        # --- Botões de ação ---
        btns = ctk.CTkFrame(c, fg_color=WHITE)
        btns.pack(fill="x", padx=24, pady=(16, 0))

        self.btn_full = ctk.CTkButton(
            btns, text="Iniciar Extracao",
            height=46, corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=GREEN, hover_color=GREEN_H, text_color=WHITE,
            command=lambda: self.iniciar(False),
        )
        self.btn_full.pack(fill="x", pady=(0, 16))

        self._divisor(c)

        sec = ctk.CTkFrame(c, fg_color=WHITE)
        sec.pack(fill="x", padx=24, pady=(12, 24))
        sec.grid_columnconfigure((0, 1), weight=1)

        self.btn_preview = ctk.CTkButton(
            sec, text="Pre-visualizar",
            height=32, corner_radius=6,
            font=ctk.CTkFont(size=11), text_color=T2,
            fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            command=self.preview_extraction,
        )
        self.btn_preview.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_cron = ctk.CTkButton(
            sec, text="Agendar",
            height=32, corner_radius=6,
            font=ctk.CTkFont(size=11), text_color=T2,
            fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            command=self._abrir_agendamento,
        )
        self.btn_cron.grid(row=0, column=1, sticky="ew")

    # ── Painel direito: Atividade ──────────────────────────────────────────────

    def _build_painel_atividade(self, parent):
        # Construir direto no pane — sem frame intermediário — para herdar o tamanho do PanedWindow
        parent.configure(fg_color=BG)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Card de status
        status_card = ctk.CTkFrame(
            parent, fg_color=WHITE, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        status_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        status_card.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(status_card, fg_color=WHITE)
        inner.pack(fill="x", padx=20, pady=18)
        inner.grid_columnconfigure(0, weight=1)

        self._lbl_status = ctk.CTkLabel(
            inner, text="Aguardando",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=T1,
        )
        self._lbl_status.grid(row=0, column=0, sticky="w")

        # Cronômetro
        timer_box = ctk.CTkFrame(inner, fg_color=GRAY_L, corner_radius=8)
        timer_box.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(timer_box, text="Tempo decorrido",
                     font=ctk.CTkFont(size=9), text_color=T3).pack(pady=(6, 0))
        self.lbl_elapsed = ctk.CTkLabel(
            timer_box, text="00:00:00",
            font=ctk.CTkFont(size=16, weight="bold", family="Consolas"),
            text_color=T2,
        )
        self.lbl_elapsed.pack(padx=20, pady=(2, 8))

        self._lbl_desc = ctk.CTkLabel(
            inner, text="Clique em 'Iniciar Extracao' para comecar.",
            font=ctk.CTkFont(size=12), text_color=T2,
        )
        self._lbl_desc.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # Label de status do agendamento
        self._lbl_agendamento = ctk.CTkLabel(
            inner, text="Agendamento inativo",
            font=ctk.CTkFont(size=11), text_color=T3,
        )
        self._lbl_agendamento.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Log de atividade
        log_card = ctk.CTkFrame(parent, fg_color=LOG_BG, corner_radius=12)
        log_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        log_hdr = ctk.CTkFrame(log_card, fg_color="#1E293B", corner_radius=0, height=36)
        log_hdr.grid(row=0, column=0, sticky="ew")
        log_hdr.grid_propagate(False)
        ctk.CTkLabel(log_hdr, text="Registro de Atividade",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#475569").pack(padx=16, side="left", anchor="w")

        self.txt_log = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=LOG_T, fg_color="transparent",
            wrap="word", corner_radius=0,
            scrollbar_button_color="#1E293B",
            scrollbar_button_hover_color="#334155",
        )
        self.txt_log.grid(row=1, column=0, sticky="nsew")

    # ── Helpers visuais ───────────────────────────────────────────────────────

    def _rotulo(self, parent, texto):
        ctk.CTkLabel(parent, text=texto,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=T1).pack(anchor="w", padx=24, pady=(20, 0))

    def _divisor(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=BORDER, corner_radius=0).pack(
            fill="x", padx=24, pady=(16, 0)
        )

    def _atualizar_status(self, titulo, descricao, cor=None):
        def _do():
            self._lbl_status.configure(text=titulo, text_color=cor or T1)
            self._lbl_desc.configure(text=descricao)
        self.after(0, _do)

    # ── Lógica principal ──────────────────────────────────────────────────────

    def pre_load_env(self):
        _exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        _env_path = os.path.join(_exe_dir, ".env")
        load_dotenv(_env_path, override=True)
        tok = os.getenv("CLICKUP_API_TOKEN", "").strip("\"'")
        if tok:
            self._token_value = tok
            os.environ["CLICKUP_API_TOKEN"] = tok
            self.conectar()
        else:
            print("Chave de acesso nao encontrada.")
            print("Clique em 'Chave de Acesso' no cabecalho para configurar.\n")

    def toggle_date(self):
        self.entry_date.configure(
            state="normal" if self.chk_date_var.get() else "disabled"
        )

    def conectar(self):
        self._set_badge("Conectando...", "#1D4ED8", "#FFFFFF")
        self._atualizar_status("Conectando...", "Verificando chave de acesso.")

        def _fetch():
            try:
                from clickup_client import ClickUpClient
                teams = ClickUpClient().get_teams()
                if not teams:
                    self._set_badge("Sem acesso", "#DC2626", "#FFFFFF")
                    self._atualizar_status(
                        "Falha na conexao",
                        "Token invalido ou sem workspaces disponiveis.", "#DC2626"
                    )
                    print("[Erro] Nenhum workspace encontrado para este token.\n")
                    return
                self.ws_map = {t["name"]: t["id"] for t in teams}

                # Carrega espaços de todos os workspaces
                client = ClickUpClient()
                space_map = {}
                for team in teams:
                    for sp in client.get_spaces(team["id"]):
                        space_map[sp["name"]] = sp["id"]

                self.after(0, lambda sm=space_map: self._popular_espacos(sm))

                nomes = ", ".join(self.ws_map.keys())
                self._set_badge(f"Conectado   {len(space_map)} espaço(s)", "#15803D", "#FFFFFF")
                self._atualizar_status(
                    "Pronto para iniciar",
                    f"{len(space_map)} espaço(s) encontrado(s) em {len(teams)} workspace(s).", GREEN
                )
                print(f"[OK] Conectado. {len(space_map)} espaço(s) encontrado(s).\n")
            except Exception as e:
                self._set_badge("Erro", "#DC2626", "#FFFFFF")
                self._atualizar_status("Erro de conexao", str(e), "#DC2626")
                print(f"[Erro] {e}\n")

        threading.Thread(target=_fetch, daemon=True).start()

    def _popular_espacos(self, space_map: dict):
        """Popula os checkboxes de espaços após conectar."""
        for w in self._space_check_frame.winfo_children():
            w.destroy()
        self._space_map = space_map
        self.space_vars = {}
        for nome in space_map:
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._space_check_frame, text=nome, variable=var,
                font=ctk.CTkFont(size=11), text_color=T1,
                fg_color=BLUE, hover_color=BLUE_H,
                checkmark_color=WHITE, corner_radius=4,
            ).pack(anchor="w", padx=12, pady=(6, 0))
            self.space_vars[nome] = var
        ctk.CTkFrame(self._space_check_frame, height=8, fg_color=GRAY_L).pack()

    def _get_selected_space_ids(self) -> str:
        """Retorna IDs dos espaços selecionados separados por vírgula."""
        return ",".join(
            self._space_map[nome]
            for nome, var in self.space_vars.items()
            if var.get() and nome in self._space_map
        )

    def iniciar(self, piloto: bool):
        token = self._token_value or os.getenv("CLICKUP_API_TOKEN", "")
        if not token:
            messagebox.showwarning(
                "Sem chave de acesso",
                "Clique em 'Chave de Acesso' no cabecalho para configurar o token.",
            )
            return

        os.environ["CLICKUP_API_TOKEN"] = token
        self._set_buttons("disabled")
        self._start_timer()

        rotulo = "Teste  —  1 lista" if piloto else "Extracao completa"
        modo = self._mode_var.get()
        self._set_badge("Em andamento", "#1D4ED8", "#FFFFFF")
        if modo == "apenas_csv":
            self._atualizar_status(
                "Exportando via navegador",
                "Abrindo ClickUp e baixando XLSX+CSV nativos → Dados_BI_ClickUp/Playwright/", BLUE,
            )
        elif modo == "apenas_csv_api":
            self._atualizar_status(
                "Extraindo via API",
                "Buscando tarefas dos espacos selecionados → Dados_BI_ClickUp/API/", BLUE,
            )
        else:
            self._atualizar_status(
                f"Em andamento  —  {rotulo}",
                "Acompanhe o progresso no Registro de Atividade abaixo.", BLUE,
            )

        space_ids = self._get_selected_space_ids()
        if not space_ids and self.space_vars:
            messagebox.showwarning(
                "Nenhum espaço selecionado",
                "Selecione ao menos um portfólio / espaço antes de iniciar.",
            )
            self._set_buttons("normal")
            self._stop_timer()
            return

        timestamp_ms = ""
        if self.chk_date_var.get():
            data_str = self.entry_date.get().strip()
            if data_str:
                try:
                    import datetime
                    dt = datetime.datetime.strptime(data_str, "%d/%m/%Y")
                    timestamp_ms = str(int(dt.timestamp() * 1000))
                except Exception:
                    print("[Aviso] Data invalida. Filtro de data ignorado.\n")

        threading.Thread(
            target=self._run_extraction,
            args=(
                piloto, space_ids, timestamp_ms,
                self.entry_sprint.get().strip(),
                self.cmb_status.get(),
                self._mode_var.get(),
            ),
            daemon=True,
        ).start()

    def _run_extraction(self, piloto, space_ids, timestamp_ms,
                        sprint_filter, status_filter, output_mode,
                        is_scheduled=False):
        try:
            sys.argv = [
                "main.py",
                "--mode", "1" if piloto else "2",
                "--space_ids", space_ids,
                "--date_gt", timestamp_ms,
                "--sprint_filter", sprint_filter,
                "--status_filter", status_filter,
                "--output_mode", output_mode,
            ]
            core_main.main()
        except Exception as e:
            print(f"\n[Erro critico] {e}")
            self.after(0, self._atualizar_status, "Erro durante a extracao", str(e), "#DC2626")
            self.after(0, self._set_badge, "Erro", "#DC2626", "#FFFFFF")
        finally:
            e = int(time.time() - (self._start_time or time.time()))
            elapsed = f"{e // 3600:02d}:{(e % 3600) // 60:02d}:{e % 60:02d}"
            self.after(0, self._stop_timer)
            self.after(0, self._set_buttons, "normal")
            self.after(0, self._set_badge, "Concluido", GREEN, "#FFFFFF")
            if output_mode == "apenas_csv":
                self.after(0, self._atualizar_status,
                           "Exportacao nativa concluida",
                           f"Tempo total: {elapsed}   Arquivos salvos em Dados_BI_ClickUp/Playwright/",
                           GREEN)
            elif output_mode == "apenas_csv_api":
                self.after(0, self._atualizar_status,
                           "Extracao API concluida",
                           f"Tempo total: {elapsed}   Arquivo salvo em Dados_BI_ClickUp/API/",
                           GREEN)
            else:
                self.after(0, self._atualizar_status,
                           "Extracao concluida",
                           f"Tempo total: {elapsed}   Arquivos salvos em Dados_Extraidos_ClickUp/",
                           GREEN)
            if is_scheduled and self._agendador.cfg.get("enviar_email"):
                arquivos = self._encontrar_arquivos_bi()
                threading.Thread(
                    target=self._agendador.enviar_email,
                    args=(arquivos,),
                    daemon=True,
                ).start()

    def preview_extraction(self):
        token = self._token_value or os.getenv("CLICKUP_API_TOKEN", "")
        if not token:
            messagebox.showwarning("Sem chave de acesso",
                                   "Configure a chave de acesso antes de continuar.")
            return

        os.environ["CLICKUP_API_TOKEN"] = token

        # Capturar ANTES da thread (tkinter não é thread-safe)
        space_ids = self._get_selected_space_ids()
        sprint_filter = self.entry_sprint.get().strip()
        status_filter = self.cmb_status.get()

        self._set_buttons("disabled")
        self._atualizar_status("Escaneando estrutura...",
                               "Listando espacos, pastas e listas disponiveis.")

        def _run():
            try:
                sys.argv = [
                    "main.py",
                    "--mode", "2",
                    "--space_ids", space_ids,
                    "--sprint_filter", sprint_filter,
                    "--status_filter", status_filter,
                    "--output_mode", "completo",
                    "--preview_only",
                ]
                core_main.main()
            except Exception as e:
                print(f"\n[Erro] {e}")
            finally:
                self._set_buttons("normal")
                self._atualizar_status("Pre-visualizacao concluida",
                                       "Veja o Registro de Atividade para a lista completa.")

        threading.Thread(target=_run, daemon=True).start()

    def _set_buttons(self, state):
        for btn in (self.btn_full, self.btn_preview, self.btn_cron):
            btn.configure(state=state)

    # ── Agendamento ───────────────────────────────────────────────────────────

    def _atualizar_label_agendamento(self, texto: str | None = None):
        cfg = self._agendador.cfg
        if texto:
            msg = texto
        elif cfg.get("ativo") and cfg.get("proxima_execucao"):
            msg = f"Agendamento ativo   Proxima: {cfg['proxima_execucao']}"
        else:
            msg = "Agendamento inativo"
        cor = GREEN if cfg.get("ativo") else T3
        self.after(0, lambda: self._lbl_agendamento.configure(text=msg, text_color=cor))

    def _executar_agendado(self, output_mode: str):
        """Callback chamado pelo Agendador quando chega a hora."""
        token = self._token_value or os.getenv("CLICKUP_API_TOKEN", "")
        if not token:
            print("[Agendador] Token nao configurado. Extracao cancelada.")
            return
        os.environ["CLICKUP_API_TOKEN"] = token
        self.after(0, self._set_buttons, "disabled")
        self.after(0, self._start_timer)
        self.after(0, self._atualizar_status,
                   "Extracao automatica em andamento",
                   "Iniciada pelo agendamento automatico.", BLUE)
        self.after(0, self._set_badge, "Em andamento", "#1D4ED8", "#FFFFFF")

        space_ids_agendados = self._agendador.cfg.get("space_ids", "")
        threading.Thread(
            target=self._run_extraction,
            args=(False, space_ids_agendados, "", "", "Todas", output_mode, True),
            daemon=True,
        ).start()

    def _encontrar_arquivos_bi(self) -> list[str]:
        """Retorna [xlsx, csv] mais recentes em Dados_BI_ClickUp ou Dados_Extraidos_ClickUp."""
        raiz = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        xlsx_candidatos: list[str] = []
        csv_candidatos: list[str] = []
        for pasta in ("Dados_BI_ClickUp", "Dados_Extraidos_ClickUp"):
            base = os.path.join(raiz, pasta)
            if not os.path.exists(base):
                continue
            try:
                for f in os.listdir(base):
                    caminho = os.path.join(base, f)
                    if f.lower().endswith(".xlsx"):
                        xlsx_candidatos.append(caminho)
                    elif f.lower().endswith(".csv"):
                        csv_candidatos.append(caminho)
            except Exception:
                pass
        resultado = []
        if xlsx_candidatos:
            resultado.append(max(xlsx_candidatos, key=os.path.getmtime))
        if csv_candidatos:
            resultado.append(max(csv_candidatos, key=os.path.getmtime))
        return resultado

    def _abrir_agendamento(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar Agendamento Automatico")
        dlg.geometry("580x620")
        dlg.resizable(False, True)
        dlg.grab_set()
        dlg.configure(fg_color=BG)

        scroll = ctk.CTkScrollableFrame(dlg, fg_color=BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        cfg = self._agendador.cfg

        def sep():
            ctk.CTkFrame(scroll, height=1, fg_color=BORDER, corner_radius=0).pack(
                fill="x", padx=24, pady=(16, 0)
            )

        def titulo(txt):
            ctk.CTkLabel(scroll, text=txt,
                         font=ctk.CTkFont(size=12, weight="bold"), text_color=T1
                         ).pack(anchor="w", padx=24, pady=(20, 0))

        # ── Ativar ──────────────────────────────────────────────────────────
        ativo_var = ctk.BooleanVar(value=bool(cfg.get("ativo")))
        ctk.CTkCheckBox(
            scroll, text="Ativar agendamento automatico",
            variable=ativo_var,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=T1,
            fg_color=BLUE, hover_color=BLUE_H, checkmark_color=WHITE, corner_radius=4,
        ).pack(anchor="w", padx=24, pady=(24, 0))

        sep()

        # ── Cronograma ──────────────────────────────────────────────────────
        titulo("Cronograma")

        # Dias da semana
        ctk.CTkLabel(scroll, text="Dias da semana",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(12, 4))

        _DIAS_KEYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
        _DIAS_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        dias_cfg = cfg.get("dias_semana", ["seg", "ter", "qua", "qui", "sex"])

        dias_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        dias_frame.pack(anchor="w", padx=24, pady=(0, 4))

        dias_vars = []
        for i, (key, lbl) in enumerate(zip(_DIAS_KEYS, _DIAS_LABELS)):
            var = ctk.BooleanVar(value=(key in dias_cfg))
            dias_vars.append(var)
            chk = ctk.CTkCheckBox(
                dias_frame, text=lbl, variable=var, width=54,
                font=ctk.CTkFont(size=11), text_color=T1,
                fg_color=BLUE, hover_color=BLUE_H, checkmark_color=WHITE, corner_radius=4,
            )
            chk.grid(row=0, column=i, padx=(0, 6))

        # Janela de horário
        ctk.CTkLabel(scroll, text="Janela de horario",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(14, 4))

        linha_janela = ctk.CTkFrame(scroll, fg_color="transparent")
        linha_janela.pack(anchor="w", padx=24, pady=(0, 4))

        ctk.CTkLabel(linha_janela, text="Inicio:", font=ctk.CTkFont(size=12), text_color=T2
                     ).grid(row=0, column=0, sticky="w")
        ent_hora_ini = ctk.CTkEntry(
            linha_janela, height=34, corner_radius=6, width=80,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text="08:00", font=ctk.CTkFont(size=12),
        )
        ent_hora_ini.grid(row=0, column=1, padx=(6, 16))
        ent_hora_ini.insert(0, cfg.get("hora_inicio", "08:00"))

        ctk.CTkLabel(linha_janela, text="Fim:", font=ctk.CTkFont(size=12), text_color=T2
                     ).grid(row=0, column=2, sticky="w")
        ent_hora_fim = ctk.CTkEntry(
            linha_janela, height=34, corner_radius=6, width=80,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text="19:00", font=ctk.CTkFont(size=12),
        )
        ent_hora_fim.grid(row=0, column=3, padx=(6, 0))
        ent_hora_fim.insert(0, cfg.get("hora_fim", "19:00"))

        # Intervalo de repetição
        ctk.CTkLabel(scroll, text="Repetir a cada",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(14, 4))

        linha_iv = ctk.CTkFrame(scroll, fg_color="transparent")
        linha_iv.pack(anchor="w", padx=24, pady=(0, 4))

        ent_iv_h = ctk.CTkEntry(
            linha_iv, height=34, corner_radius=6, width=64,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, font=ctk.CTkFont(size=12),
        )
        ent_iv_h.grid(row=0, column=0)
        ent_iv_h.insert(0, str(cfg.get("iv_horas", 1) or 0))
        ctk.CTkLabel(linha_iv, text="horas", font=ctk.CTkFont(size=12), text_color=T2
                     ).grid(row=0, column=1, padx=(6, 16))

        ent_iv_m = ctk.CTkEntry(
            linha_iv, height=34, corner_radius=6, width=64,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, font=ctk.CTkFont(size=12),
        )
        ent_iv_m.grid(row=0, column=2)
        ent_iv_m.insert(0, str(cfg.get("iv_minutos", 0) or 0))
        ctk.CTkLabel(linha_iv, text="minutos", font=ctk.CTkFont(size=12), text_color=T2
                     ).grid(row=0, column=3, padx=(6, 0))

        sep()

        # ── Modo de exportação ──────────────────────────────────────────────
        titulo("Modo de exportacao automatica")
        modo_var = ctk.StringVar(value=cfg.get("output_mode", "apenas_csv"))
        for lbl, desc, val in self._MODOS:
            bloco = ctk.CTkFrame(scroll, fg_color=BG)
            bloco.pack(fill="x", padx=24, pady=(10, 0))
            ctk.CTkRadioButton(
                bloco, text=lbl, value=val, variable=modo_var,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=T1,
                fg_color=BLUE, hover_color=BLUE_H,
            ).pack(anchor="w")
            ctk.CTkLabel(bloco, text=desc,
                         font=ctk.CTkFont(size=10), text_color=T3,
                         wraplength=480, justify="left", anchor="w",
                         ).pack(anchor="w", padx=24, pady=(2, 0))

        sep()

        # ── E-mail ──────────────────────────────────────────────────────────
        titulo("Envio por E-mail")
        email_var = ctk.BooleanVar(value=bool(cfg.get("enviar_email", True)))
        ctk.CTkCheckBox(
            scroll, text="Enviar relatorio por e-mail apos a extracao",
            variable=email_var,
            font=ctk.CTkFont(size=12), text_color=T1,
            fg_color=BLUE, hover_color=BLUE_H, checkmark_color=WHITE, corner_radius=4,
        ).pack(anchor="w", padx=24, pady=(12, 0))

        # Remetente + botão verificar
        ctk.CTkLabel(scroll, text="Seu e-mail (remetente)",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(14, 2))

        frm_rem = ctk.CTkFrame(scroll, fg_color=BG)
        frm_rem.pack(fill="x", padx=24)
        frm_rem.grid_columnconfigure(0, weight=1)

        ent_remetente = ctk.CTkEntry(
            frm_rem, height=34, corner_radius=6,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text="seu.nome@ati.pe.gov.br",
            placeholder_text_color=T3, font=ctk.CTkFont(size=12),
        )
        ent_remetente.grid(row=0, column=0, sticky="ew")
        ent_remetente.insert(0, cfg.get("remetente", ""))

        btn_enviar_cod = ctk.CTkButton(
            frm_rem, text="Enviar codigo", width=120, height=34, corner_radius=6,
            font=ctk.CTkFont(size=12), fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER, text_color=T2,
        )
        btn_enviar_cod.grid(row=0, column=1, padx=(8, 0))

        # Badge de verificação
        _ja_verificado = bool(
            cfg.get("remetente_verificado")
            and cfg.get("remetente") == ent_remetente.get().strip()
        )
        lbl_ver_status = ctk.CTkLabel(
            scroll,
            text="Email verificado" if _ja_verificado else "Nao verificado",
            font=ctk.CTkFont(size=10),
            text_color=GREEN if _ja_verificado else T3,
        )
        lbl_ver_status.pack(anchor="w", padx=24, pady=(4, 0))

        # Bloco de confirmação do código (visível após envio)
        frm_codigo = ctk.CTkFrame(scroll, fg_color=BG)
        # Não empacota ainda — aparece após envio do código

        ctk.CTkLabel(frm_codigo, text="Codigo recebido por e-mail",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", pady=(0, 4))

        linha_cod = ctk.CTkFrame(frm_codigo, fg_color=BG)
        linha_cod.pack(fill="x")
        linha_cod.grid_columnconfigure(0, weight=1)

        ent_codigo = ctk.CTkEntry(
            linha_cod, height=34, corner_radius=6, width=120,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, placeholder_text="000000",
            placeholder_text_color=T3, font=ctk.CTkFont(size=14),
        )
        ent_codigo.grid(row=0, column=0, sticky="w")

        btn_confirmar_cod = ctk.CTkButton(
            linha_cod, text="Confirmar", width=100, height=34, corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BLUE, hover_color=BLUE_H, text_color=WHITE,
        )
        btn_confirmar_cod.grid(row=0, column=1, padx=(8, 0))

        lbl_cod_msg = ctk.CTkLabel(frm_codigo, text="",
                                   font=ctk.CTkFont(size=10), text_color=T3)
        lbl_cod_msg.pack(anchor="w", pady=(4, 0))

        # Destinatários e assunto
        ctk.CTkLabel(scroll, text="Destinatarios (separados por virgula)",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(14, 2))
        ent_dest = ctk.CTkEntry(
            scroll, height=34, corner_radius=6,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, font=ctk.CTkFont(size=12),
        )
        ent_dest.pack(fill="x", padx=24)
        ent_dest.insert(0, cfg.get("destinatarios", ""))

        ctk.CTkLabel(scroll, text="Assunto  (use {data} para a data atual)",
                     font=ctk.CTkFont(size=11), text_color=T2
                     ).pack(anchor="w", padx=24, pady=(10, 2))
        ent_assunto = ctk.CTkEntry(
            scroll, height=34, corner_radius=6,
            fg_color=WHITE, border_color=BORDER, border_width=1,
            text_color=T1, font=ctk.CTkFont(size=12),
        )
        ent_assunto.pack(fill="x", padx=24)
        ent_assunto.insert(0, cfg.get("assunto", "Extrator ClickUp — Relatorio {data}"))

        sep()

        # ── Lógica de verificação ────────────────────────────────────────────
        _verificado_nesta_sessao = [_ja_verificado]

        def _enviar_codigo():
            email = ent_remetente.get().strip()
            if not email or "@" not in email:
                lbl_ver_status.configure(text="Informe um e-mail valido.", text_color=AMBER)
                return
            btn_enviar_cod.configure(state="disabled", text="Enviando...")
            lbl_ver_status.configure(text="Enviando codigo...", text_color=T3)
            _verificado_nesta_sessao[0] = False

            def _t():
                ok = self._agendador.gerar_e_enviar_codigo(email)
                if ok:
                    self.after(0, lambda: [
                        frm_codigo.pack(fill="x", padx=24, pady=(8, 0)),
                        lbl_ver_status.configure(
                            text="Codigo enviado! Verifique sua caixa de entrada.", text_color=BLUE),
                        btn_enviar_cod.configure(state="normal", text="Reenviar codigo"),
                    ])
                else:
                    self.after(0, lambda: [
                        lbl_ver_status.configure(
                            text="Falha ao enviar. Veja o Registro de Atividade.", text_color="#DC2626"),
                        btn_enviar_cod.configure(state="normal", text="Tentar novamente"),
                    ])
            threading.Thread(target=_t, daemon=True).start()

        def _confirmar_codigo():
            email = ent_remetente.get().strip()
            codigo = ent_codigo.get().strip()
            if self._agendador.verificar_codigo(email, codigo):
                _verificado_nesta_sessao[0] = True
                lbl_ver_status.configure(text="Email verificado com sucesso!", text_color=GREEN)
                lbl_cod_msg.configure(text="")
                frm_codigo.pack_forget()
                ent_codigo.delete(0, "end")
            else:
                lbl_cod_msg.configure(
                    text="Codigo incorreto ou expirado. Solicite um novo.", text_color="#DC2626")

        btn_enviar_cod.configure(command=_enviar_codigo)
        btn_confirmar_cod.configure(command=_confirmar_codigo)

        # Quando o remetente muda, reset status de verificação
        def _on_rem_change(*_):
            novo = ent_remetente.get().strip()
            if novo != cfg.get("remetente", ""):
                _verificado_nesta_sessao[0] = False
                lbl_ver_status.configure(text="Nao verificado", text_color=T3)
        ent_remetente.bind("<KeyRelease>", _on_rem_change)

        # ── Botões finais ────────────────────────────────────────────────────
        rodape = ctk.CTkFrame(scroll, fg_color=BG)
        rodape.pack(fill="x", padx=24, pady=(20, 24))
        rodape.grid_columnconfigure((0, 1), weight=1)

        def _salvar():
            remetente = ent_remetente.get().strip()
            if email_var.get() and not _verificado_nesta_sessao[0]:
                messagebox.showwarning(
                    "Remetente nao verificado",
                    "Verifique seu e-mail com o codigo antes de salvar.",
                    parent=dlg,
                )
                return
            def _int(v, default=0):
                try:
                    return max(0, int(v.strip() or str(default)))
                except (ValueError, AttributeError):
                    return default

            novo_cfg = {
                "ativo": ativo_var.get(),
                "dias_semana": [k for k, v in zip(_DIAS_KEYS, dias_vars) if v.get()],
                "hora_inicio": ent_hora_ini.get().strip() or "08:00",
                "hora_fim": ent_hora_fim.get().strip() or "19:00",
                "iv_horas": _int(ent_iv_h.get(), 1),
                "iv_minutos": _int(ent_iv_m.get(), 0),
                "ultima_execucao": cfg.get("ultima_execucao", ""),
                "output_mode": modo_var.get(),
                "enviar_email": email_var.get(),
                "remetente": remetente,
                "remetente_verificado": _verificado_nesta_sessao[0],
                "destinatarios": ent_dest.get().strip(),
                "assunto": ent_assunto.get().strip() or "Extrator ClickUp — Relatorio {data}",
                "space_ids": self._get_selected_space_ids(),
            }
            _sch_save(novo_cfg)
            self._agendador.cfg = novo_cfg
            self._agendador.recarregar()
            self._atualizar_label_agendamento()
            dlg.destroy()

            if novo_cfg.get("ativo"):
                exe_path = sys.executable if getattr(sys, "frozen", False) else None
                if exe_path:
                    ok, msg = registrar_task_scheduler(novo_cfg, exe_path)
                    if ok:
                        messagebox.showinfo(
                            "Agendamento salvo",
                            "Agendamento configurado com sucesso!\n\nTarefa registrada no Agendador de Tarefas do Windows — funcionará mesmo com o app fechado.",
                        )
                    else:
                        messagebox.showwarning(
                            "Agendamento salvo",
                            f"Agendamento salvo, mas falha ao registrar no Task Scheduler:\n{msg}",
                        )
                else:
                    messagebox.showinfo("Agendamento salvo", "Agendamento configurado com sucesso!")
            else:
                remover_task_scheduler()
                messagebox.showinfo("Agendamento salvo", "Agendamento desativado.")

        ctk.CTkButton(
            rodape, text="Cancelar",
            height=36, corner_radius=6,
            font=ctk.CTkFont(size=12), text_color=T2,
            fg_color=GRAY_L, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            command=dlg.destroy,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            rodape, text="Salvar Agendamento",
            height=36, corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BLUE, hover_color=BLUE_H, text_color=WHITE,
            command=_salvar,
        ).grid(row=0, column=1, sticky="ew")

    def create_windows_cron(self):
        """Mantido por compatibilidade — abre o novo dialog de agendamento."""
        self._abrir_agendamento()

    # ── Cronômetro ────────────────────────────────────────────────────────────

    def _start_timer(self):
        self._start_time = time.time()
        self._running = True
        self._tick()

    def _tick(self):
        if self._running and self._start_time is not None:
            e = int(time.time() - self._start_time)
            self.lbl_elapsed.configure(
                text=f"{e // 3600:02d}:{(e % 3600) // 60:02d}:{e % 60:02d}"
            )
            self._timer_job = self.after(1000, self._tick)

    def _stop_timer(self):
        self._running = False
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cron", action="store_true")
    args, _ = p.parse_known_args()

    if args.cron:
        sys.argv = ["main.py", "--mode", "2", "--output_mode", "completo"]
        core_main.main()
        sys.exit(0)

    ExtratorApp().mainloop()
