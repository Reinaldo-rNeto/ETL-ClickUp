import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import sys
import os
import shutil
from dotenv import load_dotenv

import main as core_main

# Configurações globais do tema (Base)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# PALETA PADRÃO DIGITAL PE (Aproximação Institucional)
# Azul Escuro Principal: #0C2856
# Amarelo Destaque (Bandeira): #FFCE00
# Vermelho Destaque (Bandeira): #ED282C
# Verde Acessibilidade: #27AE60
# Fundo Secundário: #121A2F (Tom dark azulado para harmonizar)

class StdoutRedirector:
    def __init__(self, text_widget, app):
        self.text_widget = text_widget
        self.app = app
        
    def write(self, text):
        self.app.after(0, self._write, text)
        
    def _write(self, text):
        self.text_widget.insert("end", text)
        self.text_widget.see("end")
        
    def flush(self): pass

class ExtratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Extrator ClickUp PRO - Padrão PE")
        self.geometry("1100x700")
        self.minsize(900, 600)
        
        # Grid Principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # ==========================================
        # 1. SIDEBAR (MENU LATERAL INSTITUCIONAL)
        # Usa o Azul Escuro Principal do Governo de Pernambuco
        # ==========================================
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color="#0C2856")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        
        self.sidebar_frame.grid_rowconfigure(5, weight=1)
        
        # Cabeçalho da Sidebar
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="ClickUp PRO", font=ctk.CTkFont(size=26, weight="bold"), text_color="#FFFFFF")
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 5))
        
        self.subtitle_label = ctk.CTkLabel(self.sidebar_frame, text="Padrão Digital PE", font=ctk.CTkFont(size=13), text_color="#A9C2E3")
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 30))
        
        # Configuração de Token
        self.lbl_token = ctk.CTkLabel(self.sidebar_frame, text="API Token de Acesso:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF")
        self.lbl_token.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.entry_token = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Ex: pk_123...", show="*", fg_color="#091B3A", border_color="#18438A", text_color="#FFFFFF")
        self.entry_token.grid(row=3, column=0, padx=20, pady=(5, 5), sticky="ew")
        
        # Botoes de Controle de Token
        self.token_btns_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.token_btns_frame.grid(row=4, column=0, padx=20, pady=(5, 20), sticky="ew")
        self.token_btns_frame.grid_columnconfigure(0, weight=1)
        self.token_btns_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_show_token = ctk.CTkButton(self.token_btns_frame, text="Visualizar", width=80, fg_color="#18438A", hover_color="#0A1C3D", text_color="#FFFFFF", command=self.toggle_token_visibility)
        self.btn_show_token.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        # Botão Autenticar usando o Amarelo do Padrão PE para chamar atenção
        self.btn_connect = ctk.CTkButton(self.token_btns_frame, text="🔌 Autenticar", width=100, font=ctk.CTkFont(weight="bold"), fg_color="#FFCE00", hover_color="#D1A700", text_color="#0C2856", command=self.load_workspaces)
        self.btn_connect.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # Ações Finais da Sidebar
        self.botoes_acao_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.botoes_acao_frame.grid(row=6, column=0, padx=20, pady=(0, 30), sticky="ew")
        
        self.btn_cron = ctk.CTkButton(self.botoes_acao_frame, text="🕒 Agendar Auto-Backup", height=40, font=ctk.CTkFont(weight="bold"), fg_color="#18438A", hover_color="#091B3A", text_color="#FFFFFF", command=self.create_windows_cron)
        self.btn_cron.pack(fill="x", pady=(0, 15))
        
        self.btn_pilot = ctk.CTkButton(self.botoes_acao_frame, text="▶ Teste Piloto (1 Lista)", height=45, font=ctk.CTkFont(weight="bold", size=14), fg_color="#D1A700", hover_color="#A38200", text_color="#FFFFFF", command=lambda: self.start_process(True))
        self.btn_pilot.pack(fill="x", pady=(0, 15))
        
        self.btn_full = ctk.CTkButton(self.botoes_acao_frame, text="⬇ EXTRAÇÃO COMPLETA", height=55, font=ctk.CTkFont(weight="bold", size=16), fg_color="#27AE60", hover_color="#1E8449", text_color="#FFFFFF", command=lambda: self.start_process(False))
        self.btn_full.pack(fill="x")
        
        # ==========================================
        # 2. PAINEL PRINCIPAL (DIREITA)
        # Trabalhando o Fundo Secundário mais escuro para evidenciar o terminal
        # ==========================================
        self.main_frame = ctk.CTkFrame(self, fg_color="#08101E") # Fundo extremamente escuro azulado
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # --- PAINEL DE FILTROS ---
        self.filters_frame = ctk.CTkFrame(self.main_frame, corner_radius=10, fg_color="#121A2F")
        self.filters_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 20))
        
        self.filters_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.lbl_workspace = ctk.CTkLabel(self.filters_frame, text="Workspace Alvo:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#E0E0E0")
        self.lbl_workspace.grid(row=0, column=0, padx=15, pady=(15, 0), sticky="w")
        self.cmb_workspace = ctk.CTkOptionMenu(self.filters_frame, values=["Todos"], dynamic_resizing=False, fg_color="#0C2856", button_color="#18438A", button_hover_color="#0A1C3D")
        self.cmb_workspace.grid(row=1, column=0, padx=15, pady=(5, 15), sticky="w")
        self.cmb_workspace.set("Todos")
        
        self.lbl_status = ctk.CTkLabel(self.filters_frame, text="Status (Estado):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#E0E0E0")
        self.lbl_status.grid(row=0, column=1, padx=15, pady=(15, 0), sticky="w")
        self.cmb_status = ctk.CTkOptionMenu(self.filters_frame, values=["Todas", "Somente Abertas", "Somente Fechadas"], dynamic_resizing=False, fg_color="#0C2856", button_color="#18438A", button_hover_color="#0A1C3D")
        self.cmb_status.grid(row=1, column=1, padx=15, pady=(5, 15), sticky="w")
        self.cmb_status.set("Todas")
        
        self.lbl_sprint = ctk.CTkLabel(self.filters_frame, text="Busca Exata (Sprint):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#E0E0E0")
        self.lbl_sprint.grid(row=0, column=2, padx=15, pady=(15, 0), sticky="w")
        self.entry_sprint = ctk.CTkEntry(self.filters_frame, placeholder_text="Ex: Sprint 2", fg_color="#091B3A", border_color="#18438A")
        self.entry_sprint.grid(row=1, column=2, padx=15, pady=(5, 15), sticky="ew")
        
        self.date_frame = ctk.CTkFrame(self.filters_frame, fg_color="transparent")
        self.date_frame.grid(row=0, column=3, rowspan=2, padx=15, pady=15, sticky="e")
        self.chk_date_var = ctk.BooleanVar(value=False)
        self.chk_date = ctk.CTkCheckBox(self.date_frame, text="Filtro Data (Pós):", variable=self.chk_date_var, command=self.toggle_date, font=ctk.CTkFont(size=12, weight="bold"), text_color="#E0E0E0", fg_color="#FFCE00", hover_color="#D1A700")
        self.chk_date.pack(side="top", anchor="w", pady=(0, 5))
        
        try:
            from tkcalendar import DateEntry
            self.entry_date = DateEntry(self.date_frame, width=15, background='#0C2856', foreground='white', borderwidth=2, date_pattern='dd/mm/yyyy', state='disabled')
            self.entry_date.pack(side="top", anchor="w")
            self.entry_date.delete(0, "end")
        except ImportError:
            self.entry_date = ctk.CTkEntry(self.date_frame, width=120, placeholder_text="DD/MM/AAAA", fg_color="#091B3A", border_color="#18438A")
            self.entry_date.pack(side="top", anchor="w")
            self.entry_date.configure(state="disabled")

        # --- CONSOLE MATRIX GOV ---
        self.log_outer_frame = ctk.CTkFrame(self.main_frame, corner_radius=15, fg_color="#05080F")
        self.log_outer_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.log_outer_frame.grid_rowconfigure(0, weight=1)
        self.log_outer_frame.grid_columnconfigure(0, weight=1)
        
        # Usando a cor de acento do Padrão PE no texto do log (Ligeiramente Amarelado/Laranja ou Cyan para leitura)
        self.text_log = ctk.CTkTextbox(self.log_outer_frame, font=ctk.CTkFont(family="Consolas", size=13), text_color="#64D2FF", fg_color="transparent", wrap="word")
        self.text_log.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        sys.stdout = StdoutRedirector(self.text_log, self)
        sys.stderr = sys.stdout 
        self.ws_map = {}
        
        self.pre_load_env()
        self.exibe_boas_vindas()

    def pre_load_env(self):
        load_dotenv()
        env_token = os.getenv("CLICKUP_API_TOKEN", "")
        if env_token:
            self.entry_token.insert(0, env_token)
            
    def exibe_boas_vindas(self):
        print(">> BEM-VINDO AO TERMINAL CORPORATIVO | PADRÃO DIGITAL PE")
        print(">> INICIALIZANDO MÓDULOS DE EXTRAÇÃO V9...\n")
        print("Interface homologada com a Paleta Institucional (Azul Principal #0C2856).")
        print("Insira seu TOKEN no painel à esquerda e clique em Autenticar para iniciar.")
        print("-" * 75)

    def toggle_token_visibility(self):
        if self.entry_token.cget("show") == "*":
            self.entry_token.configure(show="")
            self.btn_show_token.configure(text="Ocultar")
        else:
            self.entry_token.configure(show="*")
            self.btn_show_token.configure(text="Visualizar")

    def toggle_date(self):
        state = "normal" if self.chk_date_var.get() else "disabled"
        self.entry_date.configure(state=state)

    def load_workspaces(self):
        token = self.entry_token.get().strip()
        if not token:
            messagebox.showwarning("Atenção", "O Token de acesso é obrigatório!")
            return
            
        os.environ["CLICKUP_API_TOKEN"] = token
        self.btn_connect.configure(state="disabled", text="Autenticando...")
        
        def fetch():
            try:
                from clickup_client import ClickUpClient
                cli = ClickUpClient()
                teams = cli.get_teams()
                if not teams:
                    self.cmb_workspace.configure(values=["Sem Acesso"])
                    self.cmb_workspace.set("Sem Acesso")
                    print("\n[!] Falha de Autenticação: Workspace não localizado.")
                else:
                    self.ws_map = {t['name']: t['id'] for t in teams}
                    opts = ["Todos"] + list(self.ws_map.keys())
                    self.cmb_workspace.configure(values=opts)
                    self.cmb_workspace.set("Todos")
                    print("\n[+] CONEXÃO ATIVA. Acesso Válido Autorizado.")
                    print(f"      - Localizados {len(teams)} workspaces.")
            except Exception as e:
                print(f"[!] Erro ao realizar varredura na API: {e}")
            finally:
                self.btn_connect.configure(state="normal", text="🔌 Autenticar")
                
        threading.Thread(target=fetch, daemon=True).start()

    def start_process(self, is_pilot):
        token = self.entry_token.get().strip()
        if not token:
            messagebox.showwarning("Atenção", "Token não configurado na aba lateral.")
            return
            
        os.environ["CLICKUP_API_TOKEN"] = token
        self.set_buttons_state("disabled")
        print("\n" + "="*70)
        print(">>> LANÇAMENTO DO MOTOR DE EXTRATO - INICIADO")
        
        ws_selecionado = self.cmb_workspace.get()
        ws_id = self.ws_map.get(ws_selecionado, "") if ws_selecionado != "Todos" else ""
        
        date_str = self.entry_date.get().strip() if self.chk_date_var.get() else ""
        timestamp_ms = ""
        if date_str:
            print(f">>> [FILTRO] Excluindo alterações feitas antes de {date_str}")
            try:
                import datetime
                dt = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                timestamp_ms = str(int(dt.timestamp() * 1000))
            except:
                print("[AVISO] Formato de data inválido. Ignorando...")
        
        sprint_filter = self.entry_sprint.get().strip()
        status_filter = self.cmb_status.get()
        
        th = threading.Thread(target=self.run_extraction_logic, args=(is_pilot, ws_id, timestamp_ms, sprint_filter, status_filter))
        th.daemon = True
        th.start()
        
    def run_extraction_logic(self, is_pilot, ws_id, timestamp_ms, sprint_filter, status_filter):
        try:
            import os
            cwd_log = os.path.join(os.getcwd(), "LOG_MESTRE_V8.28_NA_RAIZ.txt")
            with open(cwd_log, "w", encoding="utf-8") as f:
                f.write(f"--- V9.28 INICIOU COM SUCESSO AQUI ---\nData: {timestamp_ms}\nSprint: {sprint_filter}\nStatus: {status_filter}\n")
                
            from tkinter import messagebox
            messagebox.showinfo("Automação Em Curso!", f"A automação do Extrator ClickUp foi lançada com sucesso!\n\nAcompanhe o console preenchendo as informações à direita.")
            
            print(f">>> MODO DE EXTRAÇÃO ATUAL: {'PILOTO DE LISTA ÚNICA' if is_pilot else 'VARREDURA COMPLETA'}")
            
            sys.argv = ['main.py', '--mode', '1' if is_pilot else '2', '--workspace', ws_id, '--date_gt', timestamp_ms, '--sprint_filter', sprint_filter, '--status_filter', status_filter]
            import argparse
            core_main.main()
        except Exception as e:
            print(f"\n[FALHA DE EXECUÇÃO] Exception Crítica: {e}")
        finally:
            self.set_buttons_state("normal")
            print(">>> PROCESSO CONCLUÍDO / LIBERANDO RECURSOS")

    def set_buttons_state(self, state):
        self.btn_pilot.configure(state=state)
        self.btn_full.configure(state=state)

    def create_windows_cron(self):
        token = self.entry_token.get().strip()
        if not token:
            messagebox.showwarning("Atenção", "Preencha o Token de acesso antes de agendar o script!")
            return
            
        import subprocess
        import sys
        
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        
        bat_content = f"""@echo off
echo Iniciando Backup Automatico do ClickUp (Agendado)
set CLICKUP_API_TOKEN={token}
cd /d "{os.path.dirname(exe_path)}"
"{exe_path}" --cron
"""
        bat_path = os.path.join(os.path.dirname(exe_path), "Agendador_Backup_ClickUp.bat")
        with open(bat_path, "w") as f:
            f.write(bat_content)
        
        try:
            task_cmd = f'schtasks /Create /SC WEEKLY /D FRI /TN "Backup_ClickUp_Auto" /TR "\\"{bat_path}\\"" /ST 18:00 /F'
            subprocess.run(task_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            messagebox.showinfo("Agendamento", f"O agendamento foi injetado nas tarefas do Windows.")
        except Exception as e:
            messagebox.showinfo("Agendamento Manual", f"Script gerado em:\n{bat_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cron", action="store_true", help="Background Mode")
    args, unknown = parser.parse_known_args()
    
    if args.cron:
        sys.argv = ['main.py', '--mode', '2']
        core_main.main()
        sys.exit(0)
        
    app = ExtratorApp()
    app.mainloop()
