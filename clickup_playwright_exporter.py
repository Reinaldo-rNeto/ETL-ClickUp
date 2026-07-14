"""
Exportador nativo do ClickUp via Playwright.

Fluxo exato (confirmado via capturas de tela do usuário):
  1. Login no ClickUp
  2. Navega para o espaço via URL direta: /v/o/s/{space_id}
  3. Clica na aba 'Resumo BI' na barra de tabs
  4. Clica no botão (gear) (engrenagem) no topo direito do conteúdo
     → Abre painel 'Personalizar visualização' na direita
  5. Desce no painel até 'Exportar visualização' e clica
     → Abre sub-painel de exportação com opções
  6. Seleciona formato Excel
  7. Seleciona 'Todas as colunas'
  8. Seleciona 'Total por status'
  9. Clica '↓ Baixar' para iniciar download

Credenciais lidas do .env: CLICKUP_EMAIL, CLICKUP_PASSWORD
"""

import os
import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_TEAM_ID = "9013340838"
_BASE_URL = "https://app.clickup.com"


def _safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "- " else "_" for c in text).strip()


def _screenshot(page, output_dir: str, label: str) -> str:
    try:
        debug_dir = Path(output_dir) / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = str(debug_dir / f"debug_{_safe_name(label)}.png")
        page.screenshot(path=path, full_page=False)
        return path
    except Exception:
        return ""


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page, email: str, password: str, log_fn=print) -> None:
    """Login no ClickUp. Levanta RuntimeError se 2FA ou credenciais inválidas."""
    log_fn("[PW] Abrindo página de login...")
    page.goto(f"{_BASE_URL}/login", timeout=60_000, wait_until="domcontentloaded")
    page.wait_for_timeout(2_000)

    page.wait_for_selector("input[name='email'], input[type='email']", timeout=15_000)
    page.locator("input[name='email'], input[type='email']").first.fill(email)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)

    try:
        page.wait_for_selector("input[type='password']", timeout=12_000)
    except Exception:
        pass
    page.locator("input[type='password']").first.fill(password)
    page.keyboard.press("Enter")

    try:
        page.wait_for_url(f"**/{_TEAM_ID}/**", timeout=45_000)
    except Exception:
        html = page.content().lower()
        if any(x in html for x in ["two-factor", "2fa", "verification", "mfa", "código"]):
            raise RuntimeError(
                "2FA detectada no ClickUp. Desative temporariamente a autenticação "
                "em dois fatores para usar o exportador automático."
            )
        if "login" in page.url:
            raise RuntimeError(
                "Login falhou. Verifique CLICKUP_EMAIL e CLICKUP_PASSWORD no .env."
            )

    page.wait_for_timeout(3_000)
    log_fn(f"[PW] Login concluído. URL: {page.url}")


# ── Navegação ─────────────────────────────────────────────────────────────────

def _navigate_to_space(page, space_id: str, space_name: str, log_fn=print) -> None:
    """Navega para o espaço pela URL direta (Overview) ou por clique no sidebar."""
    if space_id:
        url = f"{_BASE_URL}/{_TEAM_ID}/v/o/s/{space_id}"
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        page.wait_for_timeout(2_500)
        log_fn(f"[PW] Navegado para espaço via URL: {url}")
    else:
        # Fallback: clique na sidebar
        if _TEAM_ID not in page.url:
            page.goto(f"{_BASE_URL}/{_TEAM_ID}/", timeout=30_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
        _click_space_in_sidebar(page, space_name, log_fn)

    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    # Aguarda a barra de abas renderizar (ClickUp carrega abas progressivamente)
    try:
        page.wait_for_selector("[class*='cu-data-view-item']", timeout=20_000)
    except Exception:
        pass
    page.wait_for_timeout(3_000)


def _click_space_in_sidebar(page, space_name: str, log_fn=print) -> bool:
    """Clica no espaço na barra lateral do ClickUp (fallback)."""
    for length in [len(space_name), 25, 20, 15, 10]:
        text = space_name[:length]
        for parent_sel in [
            "nav", "[class*='sidebar']", "[class*='nav-section']",
            "[class*='spaces']", "[data-test*='sidebar']", "aside",
        ]:
            try:
                loc = page.locator(parent_sel).get_by_text(text, exact=False).first
                if loc.is_visible(timeout=2_000):
                    loc.scroll_into_view_if_needed()
                    loc.click(timeout=5_000)
                    page.wait_for_timeout(3_500)
                    log_fn(f"[PW] Sidebar: clicou em '{text}' via {parent_sel}")
                    return True
            except Exception:
                pass
        try:
            loc = page.get_by_text(text, exact=False).first
            if loc.is_visible(timeout=1_500):
                loc.scroll_into_view_if_needed()
                loc.click(timeout=5_000)
                page.wait_for_timeout(3_500)
                log_fn(f"[PW] Sidebar: clicou em '{text}' (fallback)")
                return True
        except Exception:
            pass
    return False


def _click_view_tab(page, view_name: str, log_fn=print) -> bool:
    """Clica na aba da view (ex: 'Resumo BI') na barra de tabs."""
    # ClickUp faz lazy-load das abas em headless — espera até 12s antes de tentar
    try:
        page.wait_for_selector(
            f"[role='tab']:has-text('{view_name}'), [class*='tab']:has-text('{view_name}')",
            timeout=12_000,
        )
    except Exception:
        pass

    page.wait_for_timeout(1_000)

    # Tenta via role='tab' primeiro (mais semântico)
    for sel in [
        f"[role='tab']:has-text('{view_name}')",
        f"[class*='tab']:has-text('{view_name}')",
        f"[data-test*='tab']:has-text('{view_name}')",
    ]:
        try:
            tab = page.locator(sel).first
            if tab.is_visible(timeout=2_000):
                tab.click(timeout=5_000)
                page.wait_for_timeout(3_000)
                log_fn(f"[PW] Aba '{view_name}' clicada via {sel}")
                return True
        except Exception:
            pass

    # Fallback: get_by_text (exato depois parcial)
    for exact in [True, False]:
        try:
            tab = page.get_by_text(view_name, exact=exact).first
            if tab.is_visible(timeout=3_000):
                tab.click(timeout=5_000)
                page.wait_for_timeout(3_000)
                log_fn(f"[PW] Aba '{view_name}' clicada (exact={exact})")
                return True
        except Exception:
            pass

    # Scroll horizontal na barra de abas (aba pode estar em overflow)
    log_fn(f"[PW] Tentando scroll da barra de abas para '{view_name}'...")
    for tab_sel in [
        "[class*='views-bar']", "[class*='tab-bar']", "[role='tablist']",
        "[class*='cu-tabs']", "[class*='cu-views']",
    ]:
        try:
            container = page.locator(tab_sel).first
            if not container.is_visible(timeout=1_000):
                continue
            for scroll_px in [400, 800, 1200]:
                container.evaluate(f"el => {{ el.scrollLeft = {scroll_px}; }}")
                page.wait_for_timeout(600)
                for exact in [True, False]:
                    try:
                        tab = page.get_by_text(view_name, exact=exact).first
                        if tab.is_visible(timeout=1_500):
                            tab.click(timeout=5_000)
                            page.wait_for_timeout(3_000)
                            log_fn(f"[PW] Aba '{view_name}' clicada (scroll {scroll_px}px)")
                            return True
                    except Exception:
                        pass
        except Exception:
            pass

    log_fn(f"[PW] Aba '{view_name}' não encontrada — prosseguindo com view atual")
    return False


# ── Painel de configurações da view ───────────────────────────────────────────

def _click_gear_view_settings(page, log_fn=print) -> bool:
    """
    Encontra e clica no icone de engrenagem que abre 'Personalizar visualizacao'.
    O botao fica no TOPO DIREITO do conteudo, imediatamente a esquerda de '+ Tarefa'.

    Estrategia 1: seletores diretos (data-test, aria-label)
    Estrategia 2: coordenadas relativas ao botao '+ Tarefa' (confirmado via screenshot)
    Estrategia 3: elementos clicaveis amplos (nao apenas <button>) no topo direito
    """

    def _painel_aberto() -> bool:
        try:
            return page.get_by_text("Personalizar visualização", exact=True).is_visible(timeout=1_800)
        except Exception:
            return False

    def _fechar():
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        except Exception:
            pass

    # ── Estrategia 1: seletores diretos ──────────────────────────────────────
    DIRECT = [
        "[data-test='view-settings-btn']",
        "[data-test='view-settings']",
        "[data-test='cu-view__settings']",
        "[data-test='customize-view-btn']",
        "[data-test='customize-view']",
        "[data-test='list-settings']",
        "[data-test='cu-list__customize']",
        "[data-test='list-customize']",
        "button[aria-label='Personalizar visualização']",
        "button[aria-label='Configurações da visualização']",
        "button[aria-label='Configurações']",
        "button[aria-label='Settings']",
        "button[aria-label='Customize']",
        "button[aria-label='Customize view']",
        "button[aria-label='View settings']",
    ]

    for sel in DIRECT:
        try:
            btn = page.locator(sel).first
            if not btn.is_visible(timeout=800):
                continue
            btn.click()
            page.wait_for_timeout(1_200)
            if _painel_aberto():
                log_fn(f"[PW] Painel aberto via: {sel}")
                return True
            _fechar()
        except Exception:
            pass

    # ── Estrategia 2: coordenadas relativas ao botao '+ Tarefa' ──────────────
    # Screenshot confirma: gear fica ~40-90px a esquerda de '+ Tarefa'
    log_fn("[PW] Buscando gear por coordenada relativa ao '+ Tarefa'...")
    tarefa_btn = None
    for text in ["+ Tarefa", "+ Task", "+ Cartão", "+ Card"]:
        try:
            btn = page.get_by_text(text, exact=False).last
            if btn.is_visible(timeout=1_500):
                tarefa_btn = btn
                break
        except Exception:
            pass

    if tarefa_btn:
        try:
            bb = tarefa_btn.bounding_box()
            if bb:
                cy = bb["y"] + bb["height"] / 2
                # O gear esta imediatamente antes de "+ Tarefa" (~40-100px)
                for x_offset in [-42, -65, -88, -30, -55, -78, -100, -20, -115]:
                    cx = bb["x"] + x_offset
                    if cx < 400:
                        continue
                    page.mouse.click(cx, cy)
                    page.wait_for_timeout(1_000)
                    if _painel_aberto():
                        log_fn(f"[PW] Gear encontrado: {x_offset}px a esq. de '+ Tarefa'")
                        return True
                    _fechar()
        except Exception as e:
            log_fn(f"[PW] Erro coord relativa: {e}")

    # ── Estrategia 3: elementos clicaveis amplos no topo direito ─────────────
    # ClickUp usa divs/spans clicaveis — nao apenas <button>
    log_fn("[PW] Tentativa via seletor amplo (qualquer elemento clicavel)...")
    try:
        all_els = page.locator(
            "button, [role='button'], [class*='cu-btn'], "
            "[class*='cu-icon'], [class*='toolbar__item'], "
            "[class*='header__btn'], [class*='view-header']"
        ).all()

        candidates = []
        for el in all_els:
            try:
                b = el.bounding_box()
                if b and b["x"] > 400 and 70 < b["y"] < 160 and b["width"] < 60:
                    candidates.append((el, b))
            except Exception:
                pass

        candidates.sort(key=lambda t: -t[1]["x"])
        for el, bb in candidates[:15]:
            try:
                text = el.inner_text(timeout=300).strip()
                if len(text) > 8:
                    continue
                el.click(timeout=2_000)
                page.wait_for_timeout(1_100)
                if _painel_aberto():
                    log_fn(f"[PW] Gear via seletor amplo (x={bb['x']:.0f})")
                    return True
                _fechar()
            except Exception:
                pass
    except Exception:
        pass

    return False


# ── Encontrar e clicar 'Exportar visualização' no painel ─────────────────────

def _encontrar_exportar_visualizacao(page, log_fn=print) -> bool:
    """
    No menu de contexto (ou painel), encontra 'Exportar visualizacao' e clica.
    O menu de contexto exibe a opcao diretamente (sem precisar de scroll).
    Usa selectors de texto parcial para evitar problemas de encoding Unicode.
    """
    # Seletores por texto parcial (robust contra diferenca de encoding do 'a~')
    locators = [
        # Playwright text= usa contains matching por padrao
        page.locator("text=Exportar visualização"),
        page.locator("text=Exportar visualiza"),   # parcial, ignora sufixo
        page.locator(":text-is('Exportar visualização')"),
        page.locator(":text('Exportar')").filter(has_text="visualiz"),
        page.get_by_text("Export view", exact=False),
        page.get_by_text("Exportar", exact=False),  # fallback amplo
    ]

    for loc in locators:
        try:
            el = loc.first
            if el.is_visible(timeout=1_500):
                el.click()
                page.wait_for_timeout(1_000)
                log_fn("[PW] Clicou em 'Exportar visualizacao'")
                return True
        except Exception:
            pass

    # Se nao encontrou, tenta scroll e repete (para painel de configuracoes)
    log_fn("[PW] Descendo no painel para achar opcao de exportar...")
    vp = page.viewport_size or {"width": 1920, "height": 1080}
    panel_x = int(vp["width"] * 0.87)
    panel_y = int(vp["height"] * 0.5)
    page.mouse.move(panel_x, panel_y)

    for i in range(6):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(400)
        for loc in locators[:4]:
            try:
                el = loc.first
                if el.is_visible(timeout=600):
                    el.click()
                    page.wait_for_timeout(1_000)
                    log_fn(f"[PW] Clicou em 'Exportar visualizacao' (scroll {i + 1})")
                    return True
            except Exception:
                pass

    return False


# ── Marcar opções e baixar ────────────────────────────────────────────────────

def _marcar_opcoes_e_baixar(page, space_name: str, output_dir: str,
                             log_fn=print, formato: str = "xlsx") -> list:
    """
    No diálogo de exportação:
      1. Seleciona formato (xlsx ou csv)
      2. Seleciona 'Todas as colunas'
      3. Seleciona 'Total por status' (só para xlsx)
      4. Clica 'Baixar' (captura o download)
    """
    page.wait_for_timeout(1_500)
    ts = datetime.date.today().strftime("%Y%m%d")
    safe = _safe_name(space_name)
    saved = []

    # 1. Seleciona formato
    if formato == "csv":
        for text in ["CSV", ".csv", "CSV (.csv)"]:
            try:
                el = page.get_by_text(text, exact=False).first
                if el.is_visible(timeout=3_000):
                    el.click()
                    page.wait_for_timeout(500)
                    log_fn("[PW] Formato: CSV")
                    break
            except Exception:
                pass
        ext_padrao = ".csv"
    else:
        for text in ["Excel", ".xlsx", "Excel (.xlsx)"]:
            try:
                el = page.get_by_text(text, exact=False).first
                if el.is_visible(timeout=3_000):
                    el.click()
                    page.wait_for_timeout(500)
                    log_fn("[PW] Formato: Excel")
                    break
            except Exception:
                pass
        ext_padrao = ".xlsx"

    # 2. Todas as colunas (ambos formatos)
    for text in ["Todas as colunas", "All Columns", "All columns", "Todos os campos"]:
        try:
            el = page.get_by_text(text, exact=False).first
            if el.is_visible(timeout=2_000):
                el.click()
                page.wait_for_timeout(400)
                log_fn(f"[PW] Selecionado: '{text}'")
                break
        except Exception:
            pass

    # 3. Total por status (apenas xlsx — opção pode não existir no CSV)
    if formato != "csv":
        for text in ["Total por status", "Total by Status", "Total by status"]:
            try:
                el = page.get_by_text(text, exact=False).first
                if el.is_visible(timeout=2_000):
                    el.click()
                    page.wait_for_timeout(400)
                    log_fn(f"[PW] Selecionado: '{text}'")
                    break
            except Exception:
                pass

    page.wait_for_timeout(600)

    # Screenshot antes de baixar
    shot = _screenshot(page, output_dir, f"opcoes_{formato}_{space_name}")
    if shot:
        log_fn(f"[PW] Screenshot das opcoes: {shot}")

    # 4. Clica no botão de download e captura o arquivo
    for text, exact in [("Baixar", False), ("Download", False),
                        ("Baixar", True), ("Download", True)]:
        try:
            btn = page.get_by_text(text, exact=exact).first
            if not btn.is_visible(timeout=3_000):
                continue
            log_fn(f"[PW] Clicando botao '{text}' para baixar...")
            with page.expect_download(timeout=120_000) as dl_ctx:
                btn.click()
            dl = dl_ctx.value
            ext = Path(dl.suggested_filename).suffix or ext_padrao
            fname = f"ClickUp_{safe}_{ts}{ext}"
            dest = str(Path(output_dir) / fname)
            dl.save_as(dest)
            saved.append(dest)
            log_fn(f"[PW] Arquivo salvo: {fname}")
            return saved
        except Exception as e:
            log_fn(f"[PW] Tentativa '{text}' falhou: {e}")

    return saved


# ── Export de uma view ─────────────────────────────────────────────────────────

def _dismiss_overlay(page) -> None:
    """Dispensa qualquer CDK overlay backdrop que possa estar bloqueando cliques."""
    try:
        backdrop = page.locator(".cdk-overlay-backdrop-showing").first
        if backdrop.is_visible(timeout=800):
            backdrop.click(timeout=2_000)
            page.wait_for_timeout(500)
    except Exception:
        pass
    # Pressiona Escape como garantia
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass


def _right_click_and_export(page, view_name: str, space_name: str,
                             output_dir: str, log_fn: callable,
                             formato: str) -> list:
    """
    Right-click na aba → 'Exportar visualizacao' → baixa no formato especificado.
    Aguarda o tab renderizar (headless lazy-load) antes de clicar.
    Descarta overlay CDK antes de clicar (sobra do diálogo anterior).
    """
    # Dispensa qualquer overlay residual do download anterior
    _dismiss_overlay(page)
    page.wait_for_timeout(600)

    # Aguarda o texto do tab aparecer no DOM (headless pode demorar até 10s)
    try:
        page.wait_for_selector(f":text('{view_name}')", timeout=10_000)
    except Exception:
        pass

    tab = page.get_by_text(view_name, exact=True).first
    if not tab.is_visible(timeout=4_000):
        tab = page.get_by_text(view_name, exact=False).first
    if not tab.is_visible(timeout=3_000):
        # Fallback: usa a aba ativa no momento (correta quando navegado via view_id URL)
        log_fn(f"[PW] Tab '{view_name}' nao visivel — tentando aba ativa...")
        for sel in [
            "[class*='cu-data-view-item--active']",
            "[class*='cu-data-view-item'][class*='active']",
            "[class*='data-view-item'][aria-selected='true']",
            "[role='tab'][aria-selected='true']",
        ]:
            try:
                candidate = page.locator(sel).first
                if candidate.is_visible(timeout=2_000):
                    tab = candidate
                    log_fn(f"[PW] Usando aba ativa via '{sel}'")
                    break
            except Exception:
                pass

    tab.click(button="right", timeout=8_000)
    page.wait_for_timeout(1_200)
    log_fn(f"[PW] Menu de contexto aberto ({formato.upper()}).")

    if not _encontrar_exportar_visualizacao(page, log_fn):
        shot = _screenshot(page, output_dir, f"erro_exportar_{formato}_{space_name}")
        raise RuntimeError(
            f"'Exportar visualizacao' nao encontrado para {formato}. Screenshot: {shot}"
        )

    return _marcar_opcoes_e_baixar(page, space_name, output_dir, log_fn, formato=formato)


def export_view(page, view_id: str, space_name: str, view_name: str,
                output_dir: str, log_fn=print, space_id: str = "") -> list:
    """
    Exporta uma view do ClickUp em XLSX e CSV.
    Fluxo: URL do espaço → aba 'Resumo BI' → right-click →
           'Exportar visualização' → formato → baixar  (repetido para xlsx e csv)
    """
    # 1. Navega para o espaço
    log_fn(f"[PW] Abrindo espaco: {space_name}")
    _navigate_to_space(page, space_id, space_name, log_fn)

    # 2. Left-click para ativar a view
    log_fn(f"[PW] Clicando na aba '{view_name}'...")
    found = _click_view_tab(page, view_name, log_fn)

    # Fallback 1: Overview renderiza menos abas — tenta list view do espaço
    if not found and space_id:
        alt_url = f"{_BASE_URL}/{_TEAM_ID}/v/l/s/{space_id}"
        log_fn(f"[PW] Aba nao encontrada no Overview. Tentando: {alt_url}")
        page.goto(alt_url, timeout=30_000, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        try:
            page.wait_for_selector("[class*='cu-data-view-item']", timeout=20_000)
        except Exception:
            pass
        page.wait_for_timeout(3_000)
        found = _click_view_tab(page, view_name, log_fn)

        # Para views 4-{space_id}-{seq} (exceto Overview -28), o ClickUp faz
        # Phase-2 lazy load — espera até 45s pela aba antes de desistir
        if not found and view_id and view_id.startswith("4-") and not view_id.endswith("-28"):
            log_fn(f"[PW] View especial '{view_id}' — aguardando Phase-2 tab load (45s)...")
            try:
                page.wait_for_selector(f":text('{view_name}')", timeout=45_000)
                page.wait_for_timeout(1_000)
                found = _click_view_tab(page, view_name, log_fn)
            except Exception:
                log_fn(f"[PW] '{view_name}' nao apareceu em 45s — continuando fallbacks")

    # Fallback 2: URLs alternativas para views no formato 4-{space_id}-{seq}
    if not found and space_id:
        alt_urls = [
            f"{_BASE_URL}/{_TEAM_ID}/v/t/s/{space_id}",   # table space view
            f"{_BASE_URL}/{_TEAM_ID}/v/l/s/{space_id}",   # list space view (tenta de novo)
        ]
        if view_id:
            alt_urls.insert(0, f"{_BASE_URL}/{_TEAM_ID}/v/l/{view_id}")
            alt_urls.insert(0, f"{_BASE_URL}/{_TEAM_ID}/v/t/{view_id}")

        for view_url in alt_urls:
            try:
                log_fn(f"[PW] Tentando URL: {view_url}")
                page.goto(view_url, timeout=25_000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                # Verifica se chegamos em uma página de espaço (tem tabs cu-data-view-item)
                # Se nao tiver tabs, caiu na Home/All Tasks — pula essa URL
                try:
                    page.wait_for_selector("[class*='cu-data-view-item']", timeout=8_000)
                    tabs_found = True
                except Exception:
                    tabs_found = False

                if not tabs_found:
                    log_fn(f"[PW] Sem tabs de espaco em {view_url} — pulando")
                    continue

                page.wait_for_timeout(3_000)
                found = _click_view_tab(page, view_name, log_fn)
                if found:
                    log_fn(f"[PW] Aba encontrada via: {view_url}")
                    break
            except Exception as e:
                log_fn(f"[PW] Falhou {view_url}: {e}")

    # Fallback 3: clique no sidebar para inicializar espaço completamente
    if not found and space_id:
        log_fn(f"[PW] Tentando inicializar espaco via sidebar...")
        try:
            page.goto(f"{_BASE_URL}/{_TEAM_ID}/", timeout=30_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
            for name_len in [len(space_name), 20, 15]:
                partial = space_name[:name_len]
                for sel in ["[class*='sidebar']", "nav", "aside"]:
                    try:
                        loc = page.locator(sel).get_by_text(partial, exact=False).first
                        if loc.is_visible(timeout=2_000):
                            loc.click()
                            log_fn(f"[PW] Clicou no sidebar: '{partial}'")
                            page.wait_for_timeout(5_000)
                            try:
                                page.wait_for_selector("[class*='cu-data-view-item']", timeout=20_000)
                            except Exception:
                                pass
                            page.wait_for_timeout(3_000)
                            found = _click_view_tab(page, view_name, log_fn)
                            if found:
                                break
                    except Exception:
                        pass
                if found:
                    break
        except Exception as e:
            log_fn(f"[PW] Fallback sidebar falhou: {e}")

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    page.wait_for_timeout(2_000)

    # 3. Baixa XLSX e CSV (right-click + export para cada formato)
    all_saved = []
    errors = []
    for formato in ["xlsx", "csv"]:
        log_fn(f"[PW] Exportando {formato.upper()}...")
        try:
            files = _right_click_and_export(
                page, view_name, space_name, output_dir, log_fn, formato
            )
            all_saved.extend(files)
            log_fn(f"[PW] {formato.upper()} salvo: {len(files)} arquivo(s).")
        except Exception as e:
            log_fn(f"[PW] ERRO {formato.upper()}: {e}")
            errors.append(f"{formato}: {e}")

    if not all_saved:
        shot = _screenshot(page, output_dir, f"falha_{space_name}")
        raise RuntimeError(
            f"Nenhum arquivo baixado em '{space_name}'. Erros: {errors}. Screenshot: {shot}"
        )

    return all_saved


# ── Ponto de entrada público ───────────────────────────────────────────────────

def export_resumo_bi(bi_plan: list, output_dir: str,
                     log_fn=print, headless: bool = True) -> list:
    """
    Exporta arquivos nativos do ClickUp para as views 'Resumo BI'.

    Args:
        bi_plan:    list of (space_name, view_name, view_id[, space_id])
        output_dir: pasta de destino dos arquivos baixados
        log_fn:     função de log (default: print)
        headless:   rodar sem janela (default: True)

    Returns:
        Lista de caminhos absolutos dos arquivos baixados.
    """
    import sys as _sys
    from playwright.sync_api import sync_playwright

    # Localiza o Chromium instalado no sistema quando não está no PATH padrão.
    # Necessário para exe (PyInstaller) e para ambientes como pipelines/BigData.
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        _candidates = []
        # Windows
        _local = os.environ.get("LOCALAPPDATA", "")
        if _local:
            _candidates.append(os.path.join(_local, "ms-playwright"))
        _candidates.append(os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright"))
        # Linux/macOS
        _candidates.append(os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright"))
        _candidates.append("/root/.cache/ms-playwright")
        _candidates.append("/home/.cache/ms-playwright")
        for _p in _candidates:
            if os.path.isdir(_p):
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _p
                log_fn(f"[PW] Usando browsers em: {_p}")
                break
        else:
            if getattr(_sys, "frozen", False):
                log_fn("[PW] AVISO: Chromium nao encontrado. Execute 'playwright install chromium'.")

    email = os.getenv("CLICKUP_EMAIL", "").strip("\"'")
    password = os.getenv("CLICKUP_PASSWORD", "").strip("\"'")

    if not email or not password:
        raise ValueError("CLICKUP_EMAIL e CLICKUP_PASSWORD não encontrados no .env.")

    os.makedirs(output_dir, exist_ok=True)
    all_saved = []
    errors = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()

        try:
            login(page, email, password, log_fn)

            for item in bi_plan:
                space_name = item[0]
                view_name  = item[1]
                view_id    = item[2]
                space_id   = item[3] if len(item) > 3 else ""

                log_fn(f"\n[PW] -- Exportando: {space_name} / {view_name} --")
                try:
                    files = export_view(
                        page, view_id, space_name, view_name,
                        output_dir, log_fn, space_id=space_id,
                    )
                    all_saved.extend(files)
                    log_fn(f"[PW] OK — {len(files)} arquivo(s).")
                except Exception as e:
                    log_fn(f"[PW] ERRO: {e}")
                    errors.append(f"{space_name}: {e}")

        finally:
            browser.close()

    if errors:
        log_fn(f"\n[PW] {len(errors)} erro(s) de exportação:")
        for err in errors:
            log_fn(f"  - {err}")

    if all_saved:
        log_fn(f"\n[PW] {len(all_saved)} arquivo(s) baixado(s):")
        for f in all_saved:
            log_fn(f"  -> {f}")

    return all_saved


# ── Teste standalone ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    load_dotenv()

    # view_ids e nomes confirmados via API ClickUp
    test_plan = [
        ("PORTFÓLIO DE PROJ ESTRATÉGICOS",  "Resumo BI", "8cktan6-259693",    "90131657451"),
        ("PORTFÓLIO DE ARP",                "Resumo",    "8cktan6-259093",    "90131683703"),
        ("PROJETOS CONCLUÍDOS/CANCELADOS",  "Resumo BI", "4-90131678068-23",  "90131678068"),
        ("PROJETOS SUSPENSOS/BACKLOG",       "Resumo BI", "",                   "90131746526"),
    ]
    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dados_BI_ClickUp")
    headless_mode = "--headless" in sys.argv

    print("=" * 60)
    print("Teste - Exportador Nativo ClickUp (Playwright)")
    print(f"Modo: {'headless' if headless_mode else 'VISIVEL (com janela)'}")
    print("=" * 60)

    results = export_resumo_bi(test_plan, output, headless=headless_mode)

    if results:
        print(f"\nSUCESSO - {len(results)} arquivo(s) baixado(s).")
        for r in results:
            print(f"  -> {r}")
    else:
        print("\nFALHA - nenhum arquivo foi baixado.")
        sys.exit(1)
