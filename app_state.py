"""统一应用状态管理 — 单一事实源。

替代 set.py 的全局 Tasks 和 field_schema.json 的运行时读写。
所有跨模块数据传递通过 AppState 实例完成。
"""

import json
import os
import sys

from set import TaskGroup
from lens_calc import LensParams, CalcResult, calculate, SCHEMA


def _write_root() -> str:
    """数据写入路径：打包环境=exe所在目录，开发环境=项目目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════════════════════════
#  应用状态
# ═══════════════════════════════════════════════════════════════

class AppState:
    """应用全局状态 — 单一事实源。"""

    def __init__(self):
        self.tasks: list[TaskGroup] = []
        self.lens_params: LensParams = LensParams()
        self._ctx_cache: dict | None = None
        self._params_path = os.path.join(_write_root(), "user_params.json")

    # ── Tasks 管理 ─────────────────────────────────────────

    def load_tasks(self, path: str | None = None):
        """从 JSON 加载 Tasks，替换当前全部内容。"""
        path = path or os.path.join(_write_root(), "manufacturing_process.json")
        with open(path, "r", encoding="utf-8") as f:
            groups = json.load(f)
        self.tasks.clear()
        for group in groups:
            self.tasks.append(TaskGroup(
                bay=group.get("bay", ""),
                process=group["process"],
                obj=group.get("obj", ""),
                requires=list(group["requires"]),
                row_height=group.get("row_height"),
            ))

    def save_tasks(self, path: str | None = None):
        """将当前 Tasks 写入 JSON。"""
        path = path or os.path.join(_write_root(), "manufacturing_process.json")
        data = [
            {
                "bay": g.bay,
                "process": g.process,
                "obj": g.obj,
                "requires": list(g.requires),
            }
            for g in self.tasks
        ]
        for i, g in enumerate(self.tasks):
            if g.row_height is not None:
                data[i]["row_height"] = g.row_height
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── LensParams 管理（内存操作，不读写 field_schema.json） ─

    def load_user_params(self):
        """从 user_params.json 加载用户保存的参数，叠加到默认值上。"""
        try:
            with open(self._params_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        kwargs = {}
        for k, v in saved.items():
            if hasattr(self.lens_params, k):
                kwargs[k] = v
        if kwargs:
            self.lens_params = LensParams(**kwargs)

    def save_user_params(self):
        """将当前 LensParams 保存到 user_params.json。"""
        data = {}
        for section in SCHEMA["gui_sections"]:
            for f in section["fields"]:
                if "attr" in f:
                    data[f["attr"]] = getattr(self.lens_params, f["attr"])
        with open(self._params_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update_lens_params(self, **kwargs):
        """更新透镜参数并创建新 LensParams 实例。"""
        self.lens_params = LensParams(**kwargs)

    # ── 占位符解析 ────────────────────────────────────────

    def invalidate_ctx_cache(self):
        """手动清除占位符缓存（下次 resolve 时重建）。"""
        self._ctx_cache = None

    def _build_ctx_cache(self):
        """构建 ${xxx} → 值的映射字典。"""
        r = calculate(self.lens_params)
        schema_path = os.path.join(_write_root(), "field_schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        ctx = {}
        for item in schema.get("export_ctx", []):
            if "ctx" not in item:
                continue
            src = self.lens_params if item["source"] == "params" else r
            val = getattr(src, item["attr"])
            if item.get("hide_zero"):
                try:
                    if float(val) == 0.0:
                        ctx[item["ctx"]] = ""
                        continue
                except (ValueError, TypeError):
                    if not val:
                        ctx[item["ctx"]] = ""
                        continue
            text = str(val) if item["fmt"] == "s" else format(val, item["fmt"])
            if item.get("prefix"):
                text = item["prefix"] + text
            if item.get("suffix"):
                text += item["suffix"]
            ctx[item["ctx"]] = text
        self._ctx_cache = ctx

    def resolve_placeholders(self, req: str) -> str:
        """将 ${xxx} 占位符替换为当前值。"""
        if self._ctx_cache is None:
            self._build_ctx_cache()
        result = req
        for k, v in self._ctx_cache.items():
            result = result.replace(k, v)
        return result
