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
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "materail.xlsx")


def load_materials() -> tuple[dict[str, float], list[str]]:
    """加载材料库，返回 (name_to_n, material_list)。

    - name_to_n: {材料名称: 折射率} 字典，用于 O(1) 查询
    - material_list: 按 Excel 顺序排列的材料名称列表，供下拉框显示
    """
    global _MATERIAL_CACHE
    if _MATERIAL_CACHE is not None:
        return _MATERIAL_CACHE

    path = _db_path()
    name_to_n: dict[str, float] = {}
    names: list[str] = []

    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            mat_name = str(row[0]).strip()
            if not mat_name:
                continue
            try:
                n_val = float(row[3]) if row[3] is not None else 0.0
            except (ValueError, TypeError):
                n_val = 0.0
            if mat_name not in name_to_n:
                name_to_n[mat_name] = n_val
                names.append(mat_name)
        wb.close()
    except ImportError:
        print("[material_db] 需要 openpyxl: pip install openpyxl")
    except FileNotFoundError:
        print(f"[material_db] 材料文件未找到: {path}")
    except Exception as e:
        print(f"[material_db] 读取失败: {e}")

    _MATERIAL_CACHE = (name_to_n, names)
    return _MATERIAL_CACHE


def refresh():
    """清除缓存，下次调用 load_materials 时重新读取 Excel。"""
    global _MATERIAL_CACHE
    _MATERIAL_CACHE = None
