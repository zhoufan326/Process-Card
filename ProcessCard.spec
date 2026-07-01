# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — Process Card (单文件模式)
用法: pyinstaller ProcessCard.spec
"""

import os
import sys
import re

# ── 项目路径 ──
PROJ_DIR = os.path.abspath(".")

def _p(name):
    return os.path.join(PROJ_DIR, name)

# ── 从 installer.iss 读取版本号 ──
def _get_version():
    iss_path = _p("installer.iss")
    if not os.path.isfile(iss_path):
        return "0.0.0"
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', open(iss_path, encoding="utf-8").read())
    return m.group(1) if m else "0.0.0"

VERSION = _get_version()

# ── 数据文件（会随 exe 一并分发） ──
DATAS = [
    (os.path.join(PROJ_DIR, "data", "field_schema.json"), "data"),
    (os.path.join(PROJ_DIR, "data", "manufacturing_process.json"), "data"),
    (os.path.join(PROJ_DIR, "data", "export_layout.json"), "data"),
    (os.path.join(PROJ_DIR, "materail.xlsx"), "."),
]

# ── 隐藏导入（确保 PyInstaller 完整打包这些库的所有子模块） ──
HIDDEN = [
    "openpyxl",
    "matplotlib",
    "src.material_db",
    "src.app_state",
]

# ── 明确排除 (避免 matplotlib 拖入 Qt 等) ──
EXCLUDES = [
    "PyQt5", "PyQt6", "PySide2", "PySide6",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qt4agg",
    "matplotlib.backends.backend_pyside",
    "matplotlib.backends.backend_pyside2",
    "matplotlib.backends.backend_pyside6",
    "matplotlib.backends.backend_gtk3agg",
    "matplotlib.backends.backend_gtk4agg",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_webagg",
    "matplotlib.backends.backend_webagg_core",
    "matplotlib.backends.backend_nbagg",
    "matplotlib.backends.backend_cairo",
    "notebook", "jupyter", "ipython",
    "scipy", "sympy", "pandas",
    "tornado", "zmq",
    "cv2", "sklearn", "tensorflow", "torch",
]

# ═══════════════════════════════════════════════
#  单文件模式
# ═══════════════════════════════════════════════
a = Analysis(
    [_p("src/gui.py")],
    pathex=[PROJ_DIR, os.path.join(PROJ_DIR, "src")],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"ProcessCard_v{VERSION}",
    debug=False,
    icon=_p("Optic_card.ico"),
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_architecture=None,
    codesign_identity=None,
    entitlements_file=None,
)
