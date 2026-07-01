"""材料库数据加载模块。

从 materail.xlsx 的 A 列（材料名称）和 D 列（折射率 nD）中读取材料数据，
提供下拉框所需的材料列表和折射率查询功能。
"""

import os
import sys

_MATERIAL_CACHE: tuple[dict[str, float], list[str]] | None = None


def _db_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "materail.xlsx")
    # __file__ 在 src/ 下，上级目录是项目根目录
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "materail.xlsx")


def load_materials() -> tuple[dict[str, float], list[str]]:
    """加载材料库，返回 (name_to_n, material_list)。"""
    global _MATERIAL_CACHE
    if _MATERIAL_CACHE is not None:
        return _MATERIAL_CACHE

    path = _db_path()
    name_to_n: dict[str, float] = {}
    names: list[str] = []

    if not os.path.isfile(path):
        _MATERIAL_CACHE = (name_to_n, names)
        return _MATERIAL_CACHE

    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        mat_name = str(row[0]).strip()
        if not mat_name:
            continue
        n_val = float(row[3]) if row[3] is not None else 0.0
        if mat_name not in name_to_n:
            name_to_n[mat_name] = n_val
            names.append(mat_name)
    wb.close()

    _MATERIAL_CACHE = (name_to_n, names)
    return _MATERIAL_CACHE


def refresh():
    """清除缓存，下次调用 load_materials 时重新读取 Excel。"""
    global _MATERIAL_CACHE
    _MATERIAL_CACHE = None
