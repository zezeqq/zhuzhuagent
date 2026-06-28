# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DNA Work Agent (Windows, onedir).

Build:
  powershell -ExecutionPolicy Bypass -File scripts/build.ps1
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)

import importlib.util

_identity_spec = importlib.util.spec_from_file_location(
    "app_identity", project_root / "core" / "app_identity.py"
)
_identity = importlib.util.module_from_spec(_identity_spec)
_identity_spec.loader.exec_module(_identity)
APP_BRAND_NAME = _identity.APP_NAME

datas = [
    (str(project_root / "ui" / "styles.qss"), "ui"),
    (str(project_root / "db" / "schema.sql"), "db"),
    (str(project_root / "config"), "config"),
    (str(project_root / "templates"), "templates"),
    (str(project_root / "skills"), "skills"),
]

hiddenimports = [
    "httpx",
    "httpx._transports.default",
    "httpx_sse",
    "PIL",
    "PIL.Image",
    "PIL.ImageGrab",
    "docx",
    "openpyxl",
    "pptx",
    "fitz",
    "pyautogui",
    "pyperclip",
    "uiautomation",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "numpy",
    # MCP SDK (lazy-imported in agent_runtime.mcp_client)
    "mcp",
    "mcp.client",
    "mcp.client.stdio",
    "mcp.client.sse",
    "mcp.client.streamable_http",
    "pydantic_settings",
    "sse_starlette",
    "starlette",
    "uvicorn",
    "jsonschema",
]

binaries = []

for pkg in ("PySide6", "mcp"):
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

hiddenimports += collect_submodules("ui")
hiddenimports += collect_submodules("core")
hiddenimports += collect_submodules("agent_runtime")
hiddenimports += collect_submodules("db")
hiddenimports += collect_submodules("artifacts")
hiddenimports += collect_submodules("rag")
try:
    hiddenimports += collect_submodules("mcp")
except Exception:
    pass

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "PyQt5", "PyQt6", "cv2"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_BRAND_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_BRAND_NAME,
)
