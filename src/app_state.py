"""统一应用状态管理 — 单一事实源。

所有跨模块数据传递通过 AppState 实例完成。
"""

import json
import os
import sys
from dataclasses import dataclass, field

from lens_calc import LensParams, CalcResult, calculate, SCHEMA, _data_dir


# ═══════════════════════════════════════════════════════════════
#  共享主题常量（中式古典风格）
#  主 UI (gui.py) 与子 UI (process_planning.py) 统一引用此处
# ═══════════════════════════════════════════════════════════════

CLR_PAPER = "#F5F0E8"       # 宣纸底色 – 全局背景
CLR_PANEL = "#FDF8F2"       # 面板底色 – 稍浅
CLR_HEADER = "#E8D5B7"      # 标题栏 – 暖沙色
CLR_BORDER = "#D3C1AD"      # 分隔线 – 淡茶色
CLR_TEXT = "#3E2723"        # 正文 – 深墨色
CLR_SUBTEXT = "#5D4037"     # 辅助文字 – 焦茶色
CLR_ACCENT = "#8D6E63"      # 按钮主色 – 驼棕色
CLR_ACCENT_HI = "#6D4C41"   # 按钮悬停 – 深棕
CLR_LIGHT = "#D7CCC8"       # 浅色装饰 – 米灰
CLR_TREE_GROUP = "#EDE0D4"  # Treeview 组行 – 浅砂
CLR_TREE_REQ = "#FDF8F2"    # Treeview 子行 – 米白
CLR_TREE_SEL = "#D4E6C3"    # 选中行 – 青瓷绿
FONT = "Microsoft YaHei"


@dataclass
class TaskGroup:
    """单个工序组数据。"""
    bay: str = ""
    process: str = ""
    obj: str = ""
    requires: list[str] = field(default_factory=list)
    row_height: int | float | None = None
    color: str | None = None  # 自定义颜色 hex, None=按车间匹配


def _remove_trailing_zeros(text: str) -> str:
    """移除数值字符串末尾的零和小数点。如 '48.0' → '48', '14.890' → '14.89'。"""
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _write_root() -> str:
    """数据写入路径：打包环境=exe所在目录，开发环境=项目根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════
#  应用状态
# ═══════════════════════════════════════════════════════════════

class AppState:
    """应用全局状态 — 单一事实源。"""

    def __init__(self):
        self.tasks: list[TaskGroup] = []
        self.lens_params: LensParams = LensParams()
        self._ctx_cache: dict | None = None
        self._params_path = os.path.join(_data_dir(for_write=True), "user_params.json")
        # ── 版本计数器：每次修改递增，子 UI 异步回调时校验，防竞态 ──
        self._version = 0

    @property
    def version(self) -> int:
        """当前状态版本号。异步回调返回后需与此值比对，不一致则丢弃。"""
        return self._version

    # ── Tasks 管理 ─────────────────────────────────────────

    def load_tasks(self, path: str | None = None):
        """从 JSON 加载 Tasks，替换当前全部内容。"""
        path = path or os.path.join(_data_dir(for_write=True), "manufacturing_process.json")
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
                color=group.get("color"),
            ))

    def save_tasks(self, path: str | None = None):
        """将当前 Tasks 写入 JSON。"""
        path = path or os.path.join(_data_dir(for_write=True), "manufacturing_process.json")
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
            if g.color is not None:
                data[i]["color"] = g.color
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── LensParams 管理（内存操作，不读写 field_schema.json） ─

    def load_user_params(self):
        """从 user_params.json 加载用户保存的参数，叠加到默认值上。"""
        if not os.path.isfile(self._params_path):
            return
        with open(self._params_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
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

    def apply_lens_params_to_schema(self):
        """将当前 LensParams 同步到 field_schema.json 的 default 字段。"""
        schema_path = os.path.join(_data_dir(for_write=True), "field_schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        p = self.lens_params
        for section in schema.get("gui_sections", []):
            for f in section.get("fields", []):
                if "attr" in f:
                    val = getattr(p, f["attr"], None)
                    if val is not None:
                        f["default"] = val
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)

    def update_lens_params(self, **kwargs):
        """更新透镜参数并创建新 LensParams 实例。"""
        self.lens_params = LensParams(**kwargs)
        self._version += 1

    # ── 占位符解析 ────────────────────────────────────────

    def invalidate_ctx_cache(self):
        """手动清除占位符缓存（下次 resolve 时重建）。"""
        self._ctx_cache = None

    def _build_ctx_cache(self):
        """构建 ${xxx} → 值的映射字典。"""
        r = calculate(self.lens_params)
        schema_path = os.path.join(_data_dir(), "field_schema.json")
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
            text = str(val) if item["fmt"] == "s" else _remove_trailing_zeros(format(val, item["fmt"]))
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
