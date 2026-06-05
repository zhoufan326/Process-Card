# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — Process Card (单文件模式)
用法: pyinstaller ProcessCard.spec
"""

import os
import sys

# ── 项目路径 ──
PROJ_DIR = os.path.abspath(".")

def _p(name):
    return os.path.join(PROJ_DIR, name)

# ── 数据文件（会随 exe 一并分发） ──
DATAS = [
    (_p("field_schema.json"), "."),
    (_p("manufacturing_process.json"), "."),
]

# ── 隐藏导入 ──
HIDDEN = [
    "openpyxl.cell._writer",
    "openpyxl.reader.excel",
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
    [_p("gui.py")],
    pathex=[PROJ_DIR],
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
    name="ProcessCard",
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
