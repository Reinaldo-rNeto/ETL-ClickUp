# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [
    ('agendador.py', '.'),
    ('clickup_logo.png', '.'),
    ('clickup_playwright_exporter.py', '.'),
]
binaries = []
hiddenimports = [
    # Playwright — importado dinamicamente via try/except no main.py
    'playwright',
    'playwright.sync_api',
    'playwright._impl._sync_base',
    'playwright._impl._browser',
    'playwright._impl._browser_context',
    'playwright._impl._page',
    'playwright._impl._locator',
    'playwright._impl._download',
    # python-dotenv
    'dotenv',
]
datas += collect_data_files('openpyxl')
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Inclui todos os dados do pacote Playwright (drivers, etc.)
try:
    tmp_pw = collect_all('playwright')
    datas += tmp_pw[0]; binaries += tmp_pw[1]; hiddenimports += tmp_pw[2]
except Exception:
    pass


a = Analysis(
    ['Iniciar.pyw'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Extrator_ClickUp_ATI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
