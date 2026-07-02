r"""Process Card — 流程卡片管理系统。
中式古典简约风格界面。

布局:
┌────────────────────────────────────────────┐
│  ■ Process Card    流程卡片                │
├──────────────┬─────────────────────────────┤
│  表单区       │                             │
│  车间/名称/  │      Treeview 主数据区       │
│  对象/要求   │                             │
│  [新建组]    │                             │
│  [+要求][删除]│                            │
│  [导出工艺卡] │                             │
│  [工艺计算]  │                             │
├──────────────┴─────────────────────────────┤
│  ■ 就绪（默认加载 manufacturing_process.json）  │
└────────────────────────────────────────────┘
"""

import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from app_state import AppState, TaskGroup
from app_state import CLR_PAPER, CLR_PANEL, CLR_HEADER, CLR_BORDER
from app_state import CLR_TEXT, CLR_SUBTEXT, CLR_ACCENT, CLR_ACCENT_HI
from app_state import CLR_LIGHT, CLR_TREE_GROUP, CLR_TREE_REQ, CLR_TREE_SEL, FONT
from lens_calc import LensParams, CalcResult, calculate, SCHEMA
from process_card_exporter import export_process_card
import material_db

os.environ.setdefault("MPLBACKEND", "TkAgg")

TAG_GROUP = "group"
TAG_REQ = "req"
PAD_X = 12
PAD_Y = 4


def _project_root() -> str:
    """项目根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data_dir(for_write=False) -> str:
    """JSON 数据文件目录。"""
    base = _project_root() if for_write else _project_root()
    return os.path.join(base, "data")


PROJ_DIR = _project_root()
DATA_DIR = _data_dir()
DEFAULT_JSON = os.path.join(DATA_DIR, "manufacturing_process.json")
TEMPLATE_JSON = os.path.join(DATA_DIR, "saved_process_templates.json")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _btn(parent, text, command, **kw):
    """创建风格统一的按钮。"""
    return tk.Button(
        parent, text=text, command=command,
        font=(FONT, 9), bg=CLR_ACCENT, fg="white",
        relief="flat", cursor="hand2", bd=0, padx=8, pady=3,
        activebackground=CLR_ACCENT_HI, activeforeground="white",
        **kw,
    )


def _sep(parent, row, colspan=2, pady=6):
    """横向分隔线。"""
    s = tk.Frame(parent, height=1, bg=CLR_BORDER)
    s.grid(row=row, column=0, columnspan=colspan, sticky="ew", padx=PAD_X, pady=pady)
    s.grid_propagate(False)


def _safe_close_modal(win, parent=None):
    """安全关闭模态子窗口：先释放 grab，再销毁窗口，最后让父窗口获取焦点。"""
    try:
        win.grab_release()
    except tk.TclError:
        pass
    try:
        win.destroy()
        if parent is not None:
            parent.focus_set()
    except tk.TclError:
        pass


def _make_modal(win, parent):
    """将 Toplevel 设为模态子窗口，并设置安全的关闭协议。

    创建子窗口后调用此函数代替手动 grab_set()，可确保所有关闭路径都正确释放 grab。
    返回 safe_close 函数，子窗口内部需要关闭时直接调用 safe_close() 即可。
    """
    win.transient(parent)

    def safe_close():
        _safe_close_modal(win, parent)

    win.protocol("WM_DELETE_WINDOW", safe_close)
    win.grab_set()
    return safe_close


# ── 工序模板读写 ─────────────────────────────

def _load_templates() -> list[dict]:
    """从 TEMPLATE_JSON 加载已保存的工序模板列表。"""
    if not os.path.isfile(TEMPLATE_JSON):
        return []
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f).get("templates", [])


def _save_template(name: str, group: TaskGroup):
    """将工序组保存为模板（命名去重覆盖）。"""
    templates = _load_templates()
    templates = [t for t in templates if t.get("name") != name]
    entry = {
        "name": name,
        "bay": group.bay,
        "process": group.process,
        "obj": group.obj,
        "requires": list(group.requires),
    }
    if group.row_height is not None:
        entry["row_height"] = group.row_height
    if group.color is not None:
        entry["color"] = group.color
    templates.append(entry)
    data = {"templates": templates}
    with open(TEMPLATE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _delete_template_by_index(index: int):
    """按索引删除模板并写回文件。"""
    templates = _load_templates()
    if 0 <= index < len(templates):
        templates.pop(index)
    data = {"templates": templates}
    with open(TEMPLATE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 主应用
# ──────────────────────────────────────────────

class TaskApp:
    def __init__(self, root: tk.Tk, app_state: AppState | None = None):
        self.root = root
        self.state = app_state or AppState()
        self._edit_group_idx: int | None = None
        self._edit_req_idx: int = -1
        self._dirty = False

        self._init_style()
        self._build_body()
        self._build_footer()
        self._init_drag_ctrl()
        self._bind_events()
        self.state.load_tasks()
        self._refresh_tree()
        self.bay_entry.focus_set()
        self._update_title()
        self._set_status("就绪")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ── 全局样式 ──────────────────────────────

    def _init_style(self):
        self.root.configure(bg=CLR_PAPER)
        self.root.title("Process Card · 流程管理")
        self.root.geometry("1200x700")
        self.root.minsize(960, 560)
        self.root.resizable(True, True)
        self.root.grid_columnconfigure(0, weight=2)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=CLR_TREE_REQ,
                        fieldbackground=CLR_TREE_REQ,
                        foreground=CLR_TEXT,
                        font=(FONT, 9))
        style.configure("Treeview.Heading",
                        background=CLR_HEADER,
                        foreground=CLR_TEXT,
                        font=(FONT, 9, "bold"))
        style.map("Treeview",
                  background=[("selected", CLR_TREE_SEL)],
                  foreground=[("selected", CLR_TEXT)])

    # ── 标题栏 ────────────────────────────────

    def _build_header(self):
        h = tk.Frame(self.root, bg=CLR_HEADER, height=40)
        h.grid(row=0, column=0, columnspan=2, sticky="ew")
        h.grid_propagate(False)
        tk.Label(
            h, text=chr(0x25A0) + "  Process Card  —  流程卡片管理",
            font=(FONT, 13, "bold"), fg=CLR_ACCENT, bg=CLR_HEADER,
        ).pack(side="left", padx=16, pady=8)

    # ── 主体区域 ──────────────────────────────

    def _build_body(self):
        # — 左侧面板（流程工序 Treeview，占 2/3 宽度） —
        left = tk.Frame(self.root, bg=CLR_PAPER)
        left.grid(row=0, column=0, sticky="nswe", padx=(PAD_X, 0), pady=PAD_Y)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        tk.Label(left, text="\u25a0 流程工序",
                 font=(FONT, 11, "bold"), fg=CLR_ACCENT, bg=CLR_HEADER,
                 anchor="w", padx=14).grid(row=0, column=0, sticky="ew", ipady=6)

        # ── Treeview 区域 ──
        tv_box = tk.Frame(left, bg="white",
                          highlightbackground=CLR_BORDER, highlightthickness=1)
        tv_box.grid(row=1, column=0, sticky="nswe", pady=(6, 0))
        tv_box.grid_rowconfigure(0, weight=1)
        tv_box.grid_columnconfigure(3, weight=1)

        columns = ("bay", "process", "obj", "require")
        self.tree = ttk.Treeview(tv_box, columns=columns, show="tree headings", height=20)
        self.tree.heading("#0", text="")
        self.tree.heading("bay", text="车间")
        self.tree.heading("process", text="工序")
        self.tree.heading("obj", text="对象")
        self.tree.heading("require", text="要求")
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("bay", width=75, anchor="center", stretch=False)
        self.tree.column("process", width=75, stretch=False)
        self.tree.column("obj", width=50, anchor="center", stretch=False)
        self.tree.column("require", width=400, minwidth=200, stretch=True)
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nswe", padx=2, pady=2)
        # 悬浮提示：鼠标悬停时在状态栏显示完整内容
        self._bind_tree_tooltip()

        # — 右侧面板（工序编辑 + 组属性 + 详情，占 1/3 宽度） —
        right = tk.Frame(self.root, bg=CLR_PAPER, width=320)
        right.grid(row=0, column=1, sticky="nswe", padx=PAD_X, pady=PAD_Y)
        right.grid_propagate(False)

        # 子标题
        tk.Label(right, text="\u25a0 工序编辑",
                 font=(FONT, 11, "bold"), fg=CLR_ACCENT, bg=CLR_HEADER,
                 anchor="w", padx=14).pack(fill="x", ipady=6)

        # 表单面板
        form_box = tk.Frame(right, bg=CLR_PANEL, bd=0,
                            highlightbackground=CLR_BORDER, highlightthickness=1)
        form_box.pack(fill="x", pady=(8, 0), padx=0)
        self._build_form(form_box)
        _sep(form_box, 6, colspan=2, pady=4)
        self._build_buttons(form_box)

        # ── 组属性面板（行高下拉 + 颜色选择） ──
        self._build_group_props(right)

    def _build_form(self, parent):
        """构建古典风格的标签-输入框表单。"""
        frm = tk.Frame(parent, bg=CLR_PANEL)
        frm.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        frm.grid_columnconfigure(1, weight=1)

        fields = [
            (0, "车 间", "bay_entry"),
            (1, "工 序", "process_entry"),
            (2, "对 象", "obj_entry"),
        ]
        for row, label_text, attr in fields:
            tk.Label(
                frm, text=label_text, font=(FONT, 10, "bold"),
                fg=CLR_SUBTEXT, bg=CLR_PANEL, width=6, anchor="e",
            ).grid(row=row, column=0, padx=(0, 6), pady=PAD_Y, sticky="e")
            ent = tk.Entry(
                frm, font=(FONT, 10), width=22,
                bg=CLR_LIGHT, fg=CLR_TEXT, relief="flat", bd=0,
                insertbackground=CLR_ACCENT,
            )
            ent.grid(row=row, column=1, sticky="ew", pady=PAD_Y)
            setattr(self, attr, ent)

        # 要求 — 多行输入
        tk.Label(
            frm, text="要 求", font=(FONT, 10, "bold"),
            fg=CLR_SUBTEXT, bg=CLR_PANEL, width=6, anchor="e",
        ).grid(row=3, column=0, padx=(0, 6), pady=PAD_Y, sticky="ne")
        self.req_text = tk.Text(
            frm, font=(FONT, 10), width=30, height=5,
            bg=CLR_LIGHT, fg=CLR_TEXT, relief="flat", bd=6,
            wrap="word", insertbackground=CLR_ACCENT,
        )
        self.req_text.grid(row=3, column=1, columnspan=2, sticky="ew", pady=PAD_Y)

        # 添加要求按钮（位于要求文本区右下方）
        _btn(frm, "添加/修改要求", self._on_add_require, width=10).grid(
            row=5, column=1, sticky="w", padx=(0, 14), pady=(0, 4))
        _btn(frm, "占位符", self._on_insert_placeholder, width=8).grid(
            row=5, column=2, sticky="w", padx=(0, 14), pady=(0, 4))
        frm.grid_columnconfigure(2, weight=1)

    def _build_buttons(self, parent):
        """按钮组。"""
        bf = tk.Frame(parent, bg=CLR_PANEL)
        bf.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 10))

        _btn(bf, "新建组", self._on_new, width=9).grid(row=0, column=0, padx=2, pady=2)
        _btn(bf, "删 除", self._on_delete, width=9).grid(row=0, column=1, padx=2, pady=2)
        _btn(bf, "保存工序", self._on_save_template, width=9).grid(row=1, column=0, padx=2, pady=2)
        self._insert_btn = _btn(bf, "插入组", self._on_insert_template, width=9)
        self._insert_btn.grid(row=1, column=1, padx=2, pady=2)
        _btn(bf, "管理模板", self._on_manage_templates, width=20).grid(
            row=2, column=0, columnspan=2, padx=2, pady=(6, 2), sticky="ew"
        )

        _btn(bf, "导出工艺卡", self._on_export, width=20).grid(
            row=3, column=0, columnspan=2, padx=2, pady=(6, 2), sticky="ew"
        )
        _btn(bf, "工艺计算", self._on_process_calc, width=20).grid(
            row=4, column=0, columnspan=2, padx=2, pady=2, sticky="ew"
        )

    # ── 组属性面板（行高 + 颜色，独立于表单） ──────────

    _ROW_HEIGHT_OPTIONS = ["自动", 12, 14, 16, 18, 20, 24, 28, 36, 48, 72]

    # 默认车间颜色映射（与 process_card_exporter._BAY_C 同步）
    _BAY_COLORS = {
        "成形": "00B0F0",
        "球面": "FFC000",
        "平面": "FFC000",
        "清洗": "FF0000",
        "镀膜": "00B050",
    }

    @staticmethod
    def _default_bay_color(bay: str) -> str | None:
        """根据车间名匹配默认颜色，没有匹配返回 None。"""
        for prefix, hex_val in TaskApp._BAY_COLORS.items():
            if bay.startswith(prefix):
                return hex_val
        return None

    _COLOR_OPTIONS = [
        ("默认（按车间匹配）", None),
        ("BFBFBF  —  磨边（浅灰）", "BFBFBF"),
        ("00B0F0  —  成形（蓝色）", "00B0F0"),
        ("FFC000  —  球面/平面（橙色）", "FFC000"),
        ("FF0000  —  清洗（红色）", "FF0000"),
        ("00B050  —  镀膜（绿色）", "00B050"),
    ]

    def _build_group_props(self, parent):
        box = tk.Frame(parent, bg=CLR_PANEL, bd=0,
                       highlightbackground=CLR_BORDER, highlightthickness=1)
        box.pack(fill="x", pady=(6, 0), padx=0)

        tk.Label(box, text="\u25a0 组属性",
                 font=(FONT, 10, "bold"), fg=CLR_ACCENT, bg=CLR_PANEL,
                 anchor="w", padx=14, pady=4).pack(fill="x")

        # — 行高下拉 —
        rh_frame = tk.Frame(box, bg=CLR_PANEL)
        rh_frame.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(rh_frame, text="行 高", font=(FONT, 9, "bold"),
                 fg=CLR_SUBTEXT, bg=CLR_PANEL, width=6, anchor="e"
                 ).pack(side="left", padx=(0, 6))
        self.row_height_var = tk.StringVar(value="自动")
        self.row_height_combo = ttk.Combobox(
            rh_frame, textvariable=self.row_height_var,
            values=self._ROW_HEIGHT_OPTIONS, font=(FONT, 9), width=10, state="readonly",
        )
        self.row_height_combo.pack(side="left")
        self.row_height_combo.bind("<<ComboboxSelected>>", self._on_prop_changed)
        tk.Label(rh_frame, text="磅", font=(FONT, 8), fg=CLR_SUBTEXT, bg=CLR_PANEL
                 ).pack(side="left", padx=(4, 0))

        # — 颜色选择（自定义菜单，选项文字直接显示颜色，去掉独立色块） —
        clr_frame = tk.Frame(box, bg=CLR_PANEL)
        clr_frame.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(clr_frame, text="颜 色", font=(FONT, 9, "bold"),
                 fg=CLR_SUBTEXT, bg=CLR_PANEL, width=6, anchor="e"
                 ).pack(side="left", padx=(0, 6))

        self.color_var = tk.StringVar(value="默认（按车间匹配）")
        self.color_btn = tk.Menubutton(
            clr_frame, textvariable=self.color_var,
            font=(FONT, 9), bg="white", fg=CLR_TEXT,
            relief="solid", bd=1, width=20, anchor="w",
            indicatoron=True,
        )
        self.color_btn.pack(side="left")

        color_menu = tk.Menu(self.color_btn, tearoff=False, font=(FONT, 9))
        for i, (label, hex_val) in enumerate(self._COLOR_OPTIONS):
            if hex_val:
                color_menu.add_command(
                    label=label,
                    command=lambda h=hex_val, lb=label: self._on_color_select(lb, h),
                )
                # 菜单项文字颜色 = 实际颜色
                color_menu.entryconfig(i, foreground=f"#{hex_val}")
            else:
                color_menu.add_command(
                    label=label,
                    command=lambda: self._on_color_select("默认（按车间匹配）", None),
                )
        self.color_btn.configure(menu=color_menu)

    def _on_prop_changed(self, event=None):
        """行高下拉变更时立即同步到内存并刷新树。"""
        if self._edit_group_idx is None:
            return
        self._apply_props_to_group()
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()

    def _on_color_select(self, label: str, hex_val: str | None):
        """颜色菜单选中后同步到内存并刷新树和按钮文字。"""
        self.color_var.set(label)
        if self._edit_group_idx is None:
            return
        g = self.state.tasks[self._edit_group_idx]
        g.color = hex_val
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()

    def _apply_props_to_group(self):
        """将组属性面板的值同步到当前编辑组。"""
        if self._edit_group_idx is None:
            return
        g = self.state.tasks[self._edit_group_idx]

        # 行高
        rh = self.row_height_var.get().strip()
        if rh == "自动" or not rh:
            g.row_height = None
        else:
            try:
                g.row_height = int(rh)
            except ValueError:
                g.row_height = None

    # ── 底部状态栏 ────────────────────────────

    def _build_footer(self):
        ft = tk.Frame(self.root, bg=CLR_HEADER, height=30)
        ft.grid(row=1, column=0, columnspan=2, sticky="ew")
        ft.grid_propagate(False)
        _btn(ft, "保存 (Ctrl+S)", self._save, width=14).pack(side="left", padx=8, pady=3)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(
            ft, textvariable=self.status_var, anchor="w",
            font=(FONT, 9), fg=CLR_SUBTEXT, bg=CLR_HEADER,
        ).pack(side="left", padx=16, pady=5)

    # ── 拖拽控制器 ────────────────────────────

    def _init_drag_ctrl(self):
        self._drag_ctrl = TreeDragController(
            self.tree,
            is_draggable=lambda item: item.startswith("g"),
            on_select=self._on_tree_select,
            on_move_group=self._on_move_group,
            on_move_req=self._on_move_req,
            set_status=self._set_status,
        )

    # ── 事件绑定 ──────────────────────────────

    def _bind_events(self):
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select())
        self.root.bind("<Delete>", lambda e: self._on_delete())
        self.root.bind("<Button-1>", self._on_root_click)
        self.req_text.bind("<Return>", self._on_req_enter)
        self.root.bind("<Control-s>", lambda e: self._save())
        self.root.bind("<Control-S>", lambda e: self._save())

    # ── 状态反馈 ──────────────────────────────

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    # ── 按钮忙状态管理（防重复点击） ──────────

    def _with_busy(self, buttons: list[tk.Widget], fn, status_text: str = ""):
        """执行 fn 期间禁用按钮列表，结束后恢复。"""
        for b in buttons:
            b.configure(state="disabled")
        if status_text:
            self._set_status(status_text)
        try:
            fn()
        finally:
            for b in buttons:
                b.configure(state="normal")

    # ── 脏标记 / 保存管理 ─────────────────────

    def _mark_dirty(self):
        """标记数据已修改（仅同步到内存，不写文件）。"""
        self._apply_form_to_tasks()
        self._apply_props_to_group()
        if not self._dirty:
            self._dirty = True
            self._update_title()
            self._set_status("未保存")

    def _update_title(self):
        """更新窗口标题，显示保存状态。"""
        suffix = " ● 未保存" if self._dirty else ""
        self.root.title(f"Process Card · 流程管理{suffix}")

    def _save(self):
        """保存所有数据到 JSON 文件。"""
        self._apply_form_to_tasks()
        self.state.save_tasks()                    # → manufacturing_process.json
        self.state.save_user_params()              # → user_params.json
        self.state.apply_lens_params_to_schema()   # → field_schema.json
        self._dirty = False
        self._update_title()
        self._set_status("已保存")

    def _on_closing(self):
        """关闭时检查未保存修改，询问用户。"""
        if self._dirty:
            resp = messagebox.askyesnocancel(
                "未保存",
                "当前数据尚未保存。\n\n"
                "是(Y) — 保存后关闭\n"
                "否(N) — 不保存直接关闭\n"
                "取消 — 返回继续编辑")
            if resp is None:   # 取消
                return
            if resp:           # 是 → 保存
                self._save()
        self.state.save_user_params()
        self.root.destroy()

    # ── 输入框操作 ────────────────────────────

    def _fill_inputs(self, bay="", process="", obj="", req="", row_height=""):
        for ent, val in [
            (self.bay_entry, bay), (self.process_entry, process),
            (self.obj_entry, obj),
        ]:
            ent.delete(0, tk.END)
            ent.insert(0, val)
            ent.icursor(0)
        self.req_text.delete("1.0", tk.END)
        self.req_text.insert("1.0", req)
        self.req_text.mark_set("insert", "1.0")

    def _fill_group_props(self, row_height=None, color=None):
        """填充组属性面板（行高下拉 + 颜色）。"""
        if row_height is not None:
            self.row_height_var.set(str(row_height))
        else:
            self.row_height_var.set("自动")

        if color is not None:
            for label, hex_val in self._COLOR_OPTIONS:
                if hex_val == color:
                    self.color_var.set(label)
                    break
            else:
                self.color_var.set("默认（按车间匹配）")
        else:
            self.color_var.set("默认（按车间匹配）")

    def _clear_inputs(self):
        self._fill_inputs()
        self._fill_group_props()

    def _get_req_text(self) -> str:
        return self.req_text.get("1.0", "end-1c").strip()

    # ── 实时同步：表单 → tree ────

    def _on_add_require(self):
        """添加/保存要求。"""
        if self._edit_group_idx is None:
            return
        text = self._get_req_text()
        if not text:
            return
        g = self.state.tasks[self._edit_group_idx]

        if self._edit_req_idx >= 0:
            # 编辑模式：保存修改
            g.requires[self._edit_req_idx] = text
            action = "已保存"
        else:
            # 组模式：添加为新要求，清空文本框继续录入
            g.requires.append(text)
            self.req_text.delete("1.0", tk.END)
            action = "已添加"

        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self._set_status(f"{action}要求到组 {g.process}")

    def _on_root_click(self, event=None):
        """点击非输入区域时同步表单到内存并刷新树。
        
        注意：Button 有独立的 command 回调，不应在此处重复处理。
        """
        if self._edit_group_idx is not None and event is not None:
            # Button 有自己的 command 回调；Entry/Text 正在编辑中
            if isinstance(event.widget, (tk.Entry, tk.Text, tk.Button)):
                return
            self._apply_form_to_tasks()
            self._refresh_tree()
            self._restore_selection()

    def _restore_selection(self):
        """刷新树后恢复当前编辑项的选中高亮状态。"""
        if self._edit_group_idx is None:
            return
        if self._edit_req_idx >= 0:
            item_id = self._req_item_id(self._edit_group_idx, self._edit_req_idx)
        else:
            item_id = self._group_item_id(self._edit_group_idx)
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)

    def _apply_form_to_tasks(self):
        """同步表单数据到 Tasks；编辑模式下保存要求修改。"""
        if self._edit_group_idx is None:
            return
        bay = self.bay_entry.get().strip()
        process = self.process_entry.get().strip()
        obj = self.obj_entry.get().strip()
        req = self._get_req_text()

        g = self.state.tasks[self._edit_group_idx]
        g.bay, g.process, g.obj = bay, process, obj
        if self._edit_req_idx >= 0 and req:
            g.requires[self._edit_req_idx] = req  # 编辑模式：保存修改

    # ── 占位符解析（委托给 state） ─────────────

    def _invalidate_ctx_cache(self):
        """清除占位符缓存。"""
        self.state.invalidate_ctx_cache()

    def _resolve_placeholders(self, req: str) -> str:
        """将 ${xxx} 占位符替换为当前值。"""
        return self.state.resolve_placeholders(req)

    # ── 占位符快速插入 ────────────────────────

    def _load_placeholder_map(self) -> list[tuple[str, str]]:
        """从 field_schema.json 加载占位符 → 中文标签 映射。"""
        path = os.path.join(_data_dir(), "field_schema.json")
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # attr → 中文标签（来自 gui_sections）
        attr_to_label = {}
        for section in schema.get("gui_sections", []):
            for field in section.get("fields", []):
                if "attr" in field:
                    attr_to_label[field["attr"]] = field.get("label", field["attr"])

        # 遍历 export_ctx，收集 (占位符, 描述) 列表
        placeholders: list[tuple[str, str]] = []
        for item in schema.get("export_ctx", []):
            if "ctx" not in item:
                continue
            ctx = item["ctx"]
            attr = item.get("attr", "")
            # 优先用 gui_sections 中的中文标签，其次用 export_ctx 自身的 label，最后用 attr 名
            label = attr_to_label.get(attr) or item.get("label") or attr
            placeholders.append((ctx, label))

        # 按标签排序
        placeholders.sort(key=lambda x: x[1])
        return placeholders

    def _on_insert_placeholder(self):
        """弹窗显示所有可用占位符，点击后插入到「要求」文本框光标处。"""
        placeholders = self._load_placeholder_map()
        if not placeholders:
            messagebox.showinfo("提示", "未找到可用占位符。\n请检查 field_schema.json 是否存在。")
            return

        win = tk.Toplevel(self.root)
        win.title("选择指标占位符")
        win.geometry("520x480")
        win.configure(bg=CLR_PAPER)
        safe_close = _make_modal(win, self.root)

        # 标题
        tk.Label(win, text="点击占位符即可插入到「要求」文本框当前光标位置：",
                 font=(FONT, 10), fg=CLR_SUBTEXT, bg=CLR_PAPER, anchor="w"
                 ).pack(fill="x", padx=14, pady=(10, 4))

        # 搜索框
        search_var = tk.StringVar()
        search_entry = tk.Entry(win, textvariable=search_var, font=(FONT, 10),
                                bg="white", fg=CLR_TEXT, relief="solid", bd=1)
        search_entry.pack(fill="x", padx=14, pady=(0, 6))
        search_entry.focus_set()

        # 列表容器
        container = tk.Frame(win, bg="white",
                             highlightbackground=CLR_BORDER, highlightthickness=1)
        container.pack(fill="both", expand=True, padx=14, pady=4)

        canvas = tk.Canvas(container, bg="white", highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        list_frame = tk.Frame(canvas, bg="white")
        list_frame.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _rebuild(keyword: str):
            keyword = keyword.lower()
            for w in list_frame.winfo_children():
                w.destroy()
            for ctx, label in placeholders:
                if keyword and keyword not in ctx.lower() and keyword not in label.lower():
                    continue
                _create_item(ctx, label)

        def _create_item(ctx: str, label: str):
            frm = tk.Frame(list_frame, bg="white", cursor="hand2")
            frm.pack(fill="x", padx=4, pady=1)

            ctx_lbl = tk.Label(frm, text=ctx, font=(FONT, 9, "bold"),
                               fg=CLR_ACCENT, bg="white", anchor="w", width=28)
            ctx_lbl.pack(side="left", padx=(8, 4))

            desc_lbl = tk.Label(frm, text=label, font=(FONT, 9),
                                fg=CLR_SUBTEXT, bg="white", anchor="w")
            desc_lbl.pack(side="left", fill="x", expand=True)

            # 分割线
            sep = tk.Frame(frm, height=1, bg=CLR_BORDER)
            sep.pack(fill="x", side="bottom")

            def _on_enter(_e):
                for w in (frm, ctx_lbl, desc_lbl):
                    w.configure(bg=CLR_TREE_SEL)

            def _on_leave(_e):
                for w in (frm, ctx_lbl, desc_lbl):
                    w.configure(bg="white")

            def _on_click(_e):
                self._insert_to_req_text(ctx)
                safe_close()

            for w in (frm, ctx_lbl, desc_lbl):
                w.bind("<Enter>", _on_enter)
                w.bind("<Leave>", _on_leave)
                w.bind("<Button-1>", _on_click)

        def _on_search(*_):
            _rebuild(search_var.get())

        search_var.trace_add("write", _on_search)
        _rebuild("")

        # 底部提示
        tk.Label(win, text="提示：输入关键词可快速筛选占位符",
                 font=(FONT, 8), fg=CLR_SUBTEXT, bg=CLR_PAPER, anchor="w"
                 ).pack(fill="x", padx=14, pady=(4, 8))

    def _insert_to_req_text(self, placeholder: str):
        """在要求文本框光标处插入占位符。"""
        self.req_text.insert("insert", placeholder)
        self.req_text.focus_set()

    # ── 组拖拽 ────────────────────────────────

    def _on_move_group(self, src: int, tgt: int):
        was_edit = (self._edit_group_idx == src)

        group = self.state.tasks.pop(src)

        if self._edit_group_idx is not None and not was_edit and self._edit_group_idx > src:
            self._edit_group_idx -= 1

        self.state.tasks.insert(tgt, group)

        if self._edit_group_idx is not None:
            if was_edit:
                self._edit_group_idx = tgt
            elif self._edit_group_idx >= tgt:
                self._edit_group_idx += 1
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self._set_status(f"已移动组 [{tgt + 1}] {group.process}")

    def _on_move_req(self, gi: int, src: int, tgt: int):
        """组内 req 重排。"""
        in_edit_group = (self._edit_group_idx == gi)
        was_edit_req = (in_edit_group and self._edit_req_idx == src)

        req = self.state.tasks[gi].requires.pop(src)

        if in_edit_group and not was_edit_req and self._edit_req_idx > src:
            self._edit_req_idx -= 1

        self.state.tasks[gi].requires.insert(tgt, req)

        if in_edit_group:
            if was_edit_req:
                self._edit_req_idx = tgt
            elif self._edit_req_idx >= tgt:
                self._edit_req_idx += 1
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self._set_status(f"已移动要求 [{gi + 1}.{tgt + 1}] {req[:30]}…")

    # ── Treeview 操作 ─────────────────────────

    @staticmethod
    def _group_item_id(gi: int) -> str:
        return f"g{gi}"

    @staticmethod
    def _req_item_id(gi: int, ri: int) -> str:
        return f"g{gi}_r{ri}"

    def _get_group_by_item(self, item: str) -> tuple[int, int] | None:
        if not item:
            return None
        for gi, g in enumerate(self.state.tasks):
            if item == self._group_item_id(gi):
                return (gi, -1)
            for ri in range(len(g.requires)):
                if item == self._req_item_id(gi, ri):
                    return (gi, ri)
        return None

    def _refresh_tree(self):
        tree = self.tree
        tree.tag_configure(TAG_GROUP, background=CLR_TREE_GROUP,
                           font=(FONT, 9, "bold"))
        tree.tag_configure(TAG_REQ, background=CLR_TREE_REQ,
                           font=(FONT, 9))
        tree.tag_configure("sep", background=CLR_BORDER, font=(FONT, 2))

        for item in tree.get_children():
            tree.delete(item)
        for gi, g in enumerate(self.state.tasks):
            gid = self._group_item_id(gi)
            # 确定颜色：自定义 > 车间默认 > 无
            if g.color:
                bg_hex = g.color
            else:
                bg_hex = self._default_bay_color(g.bay)

            # 仅用文字着色 + ■ 色块标记在"车间"列
            if bg_hex:
                clr_tag = f"fg_{bg_hex}"
                tree.tag_configure(clr_tag, foreground=f"#{bg_hex}",
                                   font=(FONT, 9, "bold"))
                bay_display = f"\u25a0 {g.bay}"
                tags = (clr_tag,)
            else:
                bay_display = g.bay
                tags = (TAG_GROUP,)

            tree.insert(
                "", "end", iid=gid,
                values=(bay_display, g.process, g.obj, f"\u25a0 {len(g.requires)} \u9879"),
                tags=tags,
            )
            for ri, req in enumerate(g.requires):
                resolved = self._resolve_placeholders(req)
                tree.insert(
                    gid, "end", iid=self._req_item_id(gi, ri),
                    values=("", "", "", resolved),
                    tags=(TAG_REQ,),
                )
        for item in tree.get_children():
            tree.item(item, open=True)

    # ── 选择与编辑 ────────────────────────────

    # ── Treeview 悬浮提示 ──────────────────────────

    def _bind_tree_tooltip(self):
        """鼠标移过 Treeview 行时在状态栏显示完整内容。"""
        self._tooltip_after = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self._set_status("就绪"))

    def _on_tree_motion(self, event):
        """延迟显示当前行完整内容到状态栏。"""
        if self._tooltip_after:
            self.tree.after_cancel(self._tooltip_after)
        item = self.tree.identify_row(event.y)
        if not item:
            return
        col = self.tree.identify_column(event.x)
        col_idx = int(col.replace("#", "")) - 1 if col else -1
        vals = self.tree.item(item, "values")
        if 0 <= col_idx < len(vals) and vals[col_idx]:
            info = self._get_group_by_item(item)
            if info is not None:
                gi, ri = info
                g = self.state.tasks[gi]
                prefix = f"[{gi + 1}] {g.process}  "
                text = vals[col_idx]
                self._tooltip_after = self.tree.after(
                    300, lambda t=f"{prefix}{text}": self._set_status(t[:120]))

    def _on_tree_select(self, item=None):
        if item is None:
            sel = self.tree.selection()
            if not sel:
                return
            item = sel[0]
        info = self._get_group_by_item(item)
        if info is None:
            return
        gi, ri = info
        g = self.state.tasks[gi]
        if ri == -1:
            self._edit_group_idx = gi
            self._edit_req_idx = -1
            self._fill_inputs(g.bay, g.process, g.obj, "", g.row_height)
            self._fill_group_props(g.row_height, g.color)
            self._set_status(f"选中组 [{gi + 1}] {g.process}")
        else:
            self._edit_group_idx = gi
            self._edit_req_idx = ri
            self._fill_inputs(g.bay, g.process, g.obj, g.requires[ri])
            self._set_status(f"选中 {g.process} → 要求 {ri + 1}")

    def _on_tree_double(self, event=None):
        self._on_tree_select()
        self.req_text.focus_set()

    # ── 新建 / 添加 / 删除 ────────────

    def _on_new(self):
        """在选中组的位置插入空白组，原组下移；无选中则追加末尾。"""
        insert_idx = len(self.state.tasks)
        sel = self.tree.selection()
        if sel:
            info = self._get_group_by_item(sel[0])
            if info is not None:
                gi, _ = info
                insert_idx = gi  # 在选中组的位置插入，原组被挤到下一位置

        g = TaskGroup(bay="", process="新建工序", obj="")
        self.state.tasks.insert(insert_idx, g)
        self._edit_group_idx = insert_idx
        self._edit_req_idx = -1
        self._fill_inputs("", "新建工序", "", "", "")
        self._fill_group_props()
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self.bay_entry.focus_set()
        self._set_status("新建组模式，填写后请点击保存")

    def _on_req_enter(self, event=None):
        """Enter 键确认：编辑模式→保存修改，组模式→添加为新要求。"""
        if self._edit_group_idx is None:
            return
        text = self._get_req_text()
        if not text:
            return "break"

        g = self.state.tasks[self._edit_group_idx]

        if self._edit_req_idx >= 0:
            # 编辑模式：只保存修改，不追加
            g.requires[self._edit_req_idx] = text
        else:
            # 组模式：添加为新要求，清空文本框继续录入
            g.requires.append(text)
            self.req_text.delete("1.0", tk.END)

        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self._set_status(f"已保存到组 {g.process}")
        return "break"

    def _on_delete(self):
        """选中组→删整组，选中要求→删单条。均直接删除无弹窗。"""
        sel = self.tree.selection()
        if not sel:
            return
        info = self._get_group_by_item(sel[0])
        if info is None:
            return
        gi, ri = info
        if ri == -1:
            self.state.tasks.pop(gi)
        else:
            self.state.tasks[gi].requires.pop(ri)
        self._edit_group_idx, self._edit_req_idx = None, -1
        self._clear_inputs()
        self._mark_dirty()
        self._refresh_tree()
        self._set_status("已删除")

    # ── 工序模板：保存与插入 ─────────────────

    def _on_save_template(self):
        """将当前选中组保存为工序模板。"""
        if self._edit_group_idx is None:
            messagebox.showinfo("提示", "请先选中一个工序组。")
            return

        g = self.state.tasks[self._edit_group_idx]
        from tkinter.simpledialog import askstring
        name = askstring("保存工序", "请输入工序组名称：",
                         initialvalue=g.process,
                         parent=self.root)
        if not name:
            return

        # 重名警告
        existing = _load_templates()
        if any(t.get("name") == name for t in existing):
            if not messagebox.askyesno("确认覆盖",
                    f"已存在同名工序「{name}」，是否覆盖？",
                    parent=self.root):
                return

        _save_template(name, g)
        self._set_status(f"工序「{name}」已保存")

    def _on_insert_template(self):
        """弹出下拉菜单选择已保存的工序模板，在当前位置插入。"""
        templates = _load_templates()
        if not templates:
            messagebox.showinfo("提示", "暂无已保存的工序模板。\n请先选中工序组，点击「保存工序」。")
            return

        # 创建弹出菜单
        popup = tk.Menu(self.root, tearoff=False,
                        font=(FONT, 10),
                        bg=CLR_PANEL, fg=CLR_TEXT,
                        activebackground=CLR_ACCENT, activeforeground="white")

        for t in templates:
            name = t.get("name", "未命名")
            popup.add_command(label=name,
                              command=lambda tpl=t: self._do_insert_template(tpl))

        # 在"插入组"按钮下方弹出
        btn = self._insert_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        popup.tk_popup(x, y)

    def _do_insert_template(self, template: dict):
        """将模板数据插入到当前位置。"""
        # 计算插入位置（与 _on_new 逻辑一致）
        insert_idx = len(self.state.tasks)
        sel = self.tree.selection()
        if sel:
            info = self._get_group_by_item(sel[0])
            if info is not None:
                gi, _ = info
                insert_idx = gi

        g = TaskGroup(
            bay=template.get("bay", ""),
            process=template.get("process", "工序"),
            obj=template.get("obj", ""),
            requires=list(template.get("requires", [])),
            row_height=template.get("row_height"),
            color=template.get("color"),
        )
        self.state.tasks.insert(insert_idx, g)
        self._edit_group_idx = insert_idx
        self._edit_req_idx = -1
        self._fill_inputs(g.bay, g.process, g.obj, "", g.row_height)
        self._fill_group_props(g.row_height, g.color)
        self._mark_dirty()
        self._refresh_tree()
        self._restore_selection()
        self._set_status(f"已插入工序模板「{template.get('name', '')}」")

    def _on_manage_templates(self):
        """打开模板管理窗口，可查看和删除已保存的工序模板。"""
        templates = _load_templates()
        if not templates:
            messagebox.showinfo("提示", "暂无已保存的工序模板。")
            return

        win = tk.Toplevel(self.root)
        win.title("管理工序模板")
        win.geometry("440x360")
        win.configure(bg=CLR_PAPER)
        safe_close = _make_modal(win, self.root)

        tk.Label(win, text="已保存的工序模板：", font=(FONT, 10, "bold"),
                 fg=CLR_ACCENT, bg=CLR_PAPER, anchor="w"
                 ).pack(fill="x", padx=14, pady=(10, 4))

        frm = tk.Frame(win, bg="white",
                       highlightbackground=CLR_BORDER, highlightthickness=1)
        frm.pack(fill="both", expand=True, padx=14, pady=4)
        frm.grid_columnconfigure(1, weight=1)

        for i, t in enumerate(templates):
            name = t.get("name", "未命名")
            process = t.get("process", "")
            detail = f"{name}（{process}）"

            tk.Label(frm, text=detail, font=(FONT, 9), fg=CLR_TEXT, bg="white",
                     anchor="w").grid(row=i, column=0, sticky="ew", padx=(8, 4), pady=3)

            def _del(idx=i):
                _delete_template_by_index(idx)
                self._set_status("模板已删除")
                safe_close()

            tk.Button(frm, text="删除", command=_del,
                      font=(FONT, 8), fg="white", bg="#c0392b",
                      relief="flat", cursor="hand2", bd=0, padx=8, pady=1
                      ).grid(row=i, column=1, padx=(4, 8), pady=3)

        tk.Button(win, text="关闭", command=safe_close,
                  font=(FONT, 9), bg=CLR_ACCENT, fg="white",
                  relief="flat", cursor="hand2", bd=0, padx=12, pady=3
                  ).pack(pady=(4, 10))

    # ── 导出工艺卡 / 工艺计算 ────────────────

    def _on_export(self):
        """导出完整工艺卡片 Excel。"""
        filepath = filedialog.asksaveasfilename(
            title="导出工艺卡片",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")],
        )
        if not filepath:
            return
        try:
            export_process_card(filepath, lens_params=self.state.lens_params,
                                tasks=self.state.tasks)
            messagebox.showinfo("导出完成", f"工艺卡片已生成:\n{filepath}")
            self._set_status("工艺卡已导出")
        except PermissionError:
            messagebox.showwarning("文件被占用",
                                   "导出失败，文件正在被 Excel 或其他程序打开。\n请先关闭文件再重试。")

    def _on_process_calc(self):
        """打开工艺计算窗口（Toplevel 子窗口，共享 AppState）。

        使用回调模式：
        - 子 UI (ProcessPlanApp) 通过 on_apply_callback 通知主 UI 参数已更新
        - 主 UI 收到回调后刷新缓存和树
        - 子 UI 不再直接写 field_schema.json，改为委托给主 UI
        """

        def _on_lens_applied():
            """子 UI 应用参数后的回调 —— 主 UI 统一处理刷新生效。"""
            self._invalidate_ctx_cache()
            self._mark_dirty()
            self._refresh_tree()
            self._restore_selection()
            self._set_status("参数已同步（未保存）")

        calc_root = tk.Toplevel(self.root)
        ProcessPlanApp(
            calc_root,
            app_state=self.state,
            on_apply_callback=_on_lens_applied,
        )
        calc_root.transient(self.root)
        calc_root.grab_set()
        self.root.wait_window(calc_root)


# ═══════════════════════════════════════════════════════════════
#  TreeDragController — Treeview 拖拽交互组件
# ═══════════════════════════════════════════════════════════════

class TreeDragController:
    """控制 ttk.Treeview 的拖拽与选择交互。"""

    def __init__(self, tree, *, is_draggable, on_select=None,
                 on_move_group=None, on_move_req=None, set_status=None):
        self._tree = tree
        self._is_draggable = is_draggable
        self._on_select = on_select
        self._on_move_group = on_move_group
        self._on_move_req = on_move_req
        self._set_status = set_status
        self._drag_src_item = None
        self._drag_tgt_item = None
        self._drag_did_move = False
        self._bind_events()

    def _bind_events(self):
        self._tree.bind("<Button-1>", self._on_press)
        self._tree.bind("<B1-Motion>", self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_release)

    @staticmethod
    def _parse(item: str):
        if not item or not item.startswith("g"):
            return None, None
        parts = item.split("_")
        try:
            gi = int(parts[0][1:])
        except ValueError:
            return None, None
        ri = None
        if len(parts) == 2 and parts[1].startswith("r"):
            try:
                ri = int(parts[1][1:])
            except ValueError:
                pass
        return gi, ri

    def _can_drag(self, item: str) -> bool:
        if not item or not self._is_draggable(item):
            return False
        gi, ri = self._parse(item)
        if gi is None:
            return False
        return ri is None or len(self._tree.get_children(f"g{gi}")) >= 2

    def _on_press(self, event):
        item = self._tree.identify_row(event.y)
        if not self._can_drag(item):
            self._drag_src_item = None
            self._drag_did_move = False
            return
        self._drag_src_item = item
        self._drag_tgt_item = None
        self._drag_did_move = False

    def _on_drag_motion(self, event):
        if self._drag_src_item is None:
            return
        item = self._tree.identify_row(event.y)
        if not self._can_drag(item) or item == self._drag_src_item:
            return
        if item == self._drag_tgt_item:
            return
        self._drag_did_move = True
        self._drag_tgt_item = item
        self._tree.selection_set(item)
        s_gi, s_ri = self._parse(self._drag_src_item)
        t_gi, t_ri = self._parse(item)
        if s_ri is None and t_ri is None:
            msg = f"拖拽组 [{s_gi + 1}] → 目标 [{t_gi + 1}]"
        elif s_ri is not None and t_ri is not None and s_gi == t_gi:
            msg = f"拖拽要求 [{s_gi + 1}.{s_ri + 1}] → 目标 [{t_gi + 1}.{t_ri + 1}]"
        else:
            return
        if self._set_status:
            self._set_status(msg)

    def _on_release(self, event):
        if not self._drag_did_move or self._drag_src_item is None or self._drag_tgt_item is None:
            self._clear()
            item = self._tree.identify_row(event.y)
            if item and self._on_select:
                self._on_select(item)
            return
        s_gi, s_ri = self._parse(self._drag_src_item)
        t_gi, t_ri = self._parse(self._drag_tgt_item)
        if s_ri is None and t_ri is None:
            if self._on_move_group:
                self._on_move_group(s_gi, t_gi)
            self._tree.selection_set(f"g{t_gi}")
        elif s_ri is not None and t_ri is not None and s_gi == t_gi:
            if self._on_move_req:
                self._on_move_req(s_gi, s_ri, t_ri)
            self._tree.selection_set(self._drag_tgt_item)
        self._clear()

    def _clear(self):
        self._drag_src_item = None
        self._drag_tgt_item = None
        self._drag_did_move = False


# ═══════════════════════════════════════════════════════════════
#  ProcessPlanApp — 工艺方案计算子窗口 (由 TaskApp._on_process_calc 启动)
# ═══════════════════════════════════════════════════════════════

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


class ProcessPlanApp:
    """球面透镜工艺计算 GUI。

    通信契约（单向数据流）：
    - 子 UI 通过 on_apply_callback 回调通知主 UI 参数已变更
    - 子 UI 不直接写 field_schema.json，持久化由主 UI 统一处理
    """

    def __init__(self, root, app_state=None, on_apply_callback=None):
        self.root = root
        self.state = app_state or AppState()
        self._params = self.state.lens_params
        self._material_dict, self._material_list = material_db.load_materials()
        self._last_result = None
        self._destroyed = False
        self._on_apply_callback = on_apply_callback
        self._action_buttons = []
        self._build_ui()
        self._on_calculate()

    def _build_ui(self):
        r = self.root
        r.title("Process Card · 工艺方案计算")
        r.geometry("1100x660")
        r.minsize(900, 500)
        r.configure(bg=CLR_PAPER)

        h = tk.Frame(r, bg=CLR_HEADER, height=38)
        h.pack(fill="x")
        h.pack_propagate(False)
        tk.Label(h, text="\u25a0  球面透镜工艺方案设计计算",
                 font=(FONT, 12, "bold"), fg=CLR_ACCENT, bg=CLR_HEADER).pack(
                     side="left", padx=16, pady=6)
        main = tk.Frame(r, bg=CLR_PAPER)
        main.pack(fill="both", expand=True, padx=8, pady=4)
        self._build_input_panel(main)
        self._build_result_panel(main)
        self._build_footer(r)

    def _build_input_panel(self, parent):
        left = tk.Frame(parent, bg=CLR_PANEL,
                        highlightbackground=CLR_BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=False, padx=(0, 4))
        canvas = tk.Canvas(left, bg=CLR_PANEL, width=420, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        panel = tk.Frame(canvas, bg=CLR_PANEL)
        panel.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=panel, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda e2: self._on_canvas_scroll(e2, canvas)))
        canvas.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._build_input_fields(panel)

    def _on_canvas_scroll(self, event, canvas):
        if self._destroyed:
            return
        canvas.yview_scroll(int(-event.delta / 120), "units")

    def _build_result_panel(self, parent):
        right = tk.Frame(parent, bg=CLR_PANEL,
                         highlightbackground=CLR_BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        self._result = tk.Text(right, font=("Consolas", 11), bg="#FAFAFA",
                               fg=CLR_TEXT, wrap="word", state="disabled",
                               padx=10, pady=10)
        self._result.pack(fill="both", expand=True, padx=2, pady=2)

    def _build_footer(self, root):
        bf = tk.Frame(root, bg=CLR_HEADER, height=40)
        bf.pack(fill="x")
        bf.pack_propagate(False)
        btn_kw = dict(font=(FONT, 10, "bold"), bg=CLR_ACCENT, fg="white",
                      relief="flat", cursor="hand2", bd=0,
                      activebackground=CLR_ACCENT_HI, activeforeground="white")
        calc_btn = tk.Button(bf, text="开始计算", command=self._on_calculate,
                             **btn_kw, width=12)
        calc_btn.pack(side="left", padx=14, pady=5)
        apply_btn = tk.Button(bf, text="应用", command=self._on_apply,
                              **btn_kw, width=12)
        apply_btn.pack(side="left", padx=4, pady=5)
        show_btn = tk.Button(bf, text="展示计算过程", command=self._show_calculation_process,
                             **btn_kw, width=14)
        show_btn.pack(side="left", padx=4, pady=5)
        self._action_buttons = [calc_btn, apply_btn, show_btn]
        self._status = tk.StringVar(value="就绪 — 请输入参数后点击「开始计算」")
        tk.Label(bf, textvariable=self._status, font=(FONT, 9),
                 fg=CLR_SUBTEXT, bg=CLR_HEADER, anchor="e"
                 ).pack(side="right", padx=16, pady=5)

    def _with_busy(self, fn):
        for b in self._action_buttons:
            b.configure(state="disabled")
        try:
            fn()
        finally:
            if not self._destroyed:
                for b in self._action_buttons:
                    b.configure(state="normal")

    def _on_closing(self):
        self._destroyed = True
        self.root.unbind_all("<MouseWheel>")
        self.root.grab_release()
        self.root.destroy()

    def _build_input_fields(self, panel):
        self._entries = {}
        _DEFAULTS = self.state.lens_params
        _row = [0]

        def _section(title):
            tk.Label(panel, text=title, font=(FONT, 10, "bold"),
                     fg=CLR_ACCENT, bg=CLR_PANEL, anchor="w").grid(
                         row=_row[0], column=0, columnspan=2,
                         sticky="ew", padx=14, pady=(10, 2))
            _row[0] += 1

        def _add_field(attr, label, unit=""):
            default = str(getattr(_DEFAULTS, attr))
            tk.Label(panel, text=label, font=(FONT, 9), fg=CLR_SUBTEXT,
                     bg=CLR_PANEL, anchor="e", width=18).grid(
                         row=_row[0], column=0, padx=(14, 4), pady=2, sticky="e")
            frm = tk.Frame(panel, bg=CLR_PANEL)
            frm.grid(row=_row[0], column=1, sticky="ew", padx=(0, 14), pady=2)
            if attr == "coating_spec":
                ent = tk.Text(frm, font=(FONT, 9), width=30, height=4,
                              bg="white", fg=CLR_TEXT, relief="solid", bd=1,
                              wrap="word", insertbackground=CLR_ACCENT)
                ent.pack(fill="x")
                ent.insert("1.0", default)
                ent.mark_set("insert", "1.0")
            elif attr == "material":
                ent = ttk.Combobox(frm, values=self._material_list,
                                   font=(FONT, 9), width=18)
                ent.pack(side="left")
                ent.set(default)
                ent.bind("<<ComboboxSelected>>", self._on_material_changed)
                ent.bind("<KeyRelease>", self._on_material_changed)
            else:
                ent = tk.Entry(frm, font=(FONT, 9), width=18, bg="white",
                               fg=CLR_TEXT, relief="solid", bd=1)
                ent.pack(side="left")
                ent.insert(0, default)
                ent.icursor(0)
            if unit:
                tk.Label(frm, text=unit, font=(FONT, 8), fg=CLR_SUBTEXT,
                         bg=CLR_PANEL).pack(side="left", padx=(4, 0))
            self._entries[attr] = ent
            _row[0] += 1

        for section in SCHEMA["gui_sections"]:
            _section(section["title"])
            for f in section["fields"]:
                if "attr" not in f:
                    continue
                _add_field(f["attr"], f["label"], f.get("unit", ""))

        self._entry_order = []
        for section in SCHEMA["gui_sections"]:
            for f in section["fields"]:
                if "attr" not in f or f["attr"] not in self._entries:
                    continue
                w = self._entries[f["attr"]]
                if isinstance(w, ttk.Combobox):
                    continue
                self._entry_order.append(w)

        def _nav(delta):
            if self._destroyed:
                return
            focused = self.root.focus_get()
            for i, w in enumerate(self._entry_order):
                if w == focused:
                    target = (i + delta) % len(self._entry_order)
                    self._entry_order[target].focus_set()
                    return
            if self._entry_order:
                self._entry_order[0].focus_set()

        for w in self._entry_order:
            w.bind("<Down>", lambda e, d=+1: _nav(d), add="+")
            w.bind("<Up>", lambda e, d=-1: _nav(d), add="+")
        self._on_material_changed()

    def _on_material_changed(self, event=None):
        if self._destroyed:
            return
        if "material" not in self._entries or "n" not in self._entries:
            return
        name = self._entries["material"].get().strip()
        n_val = self._material_dict.get(name)
        if n_val is not None and n_val > 0:
            n_ent = self._entries["n"]
            old = n_ent.get().strip()
            new = str(n_val)
            if old != new:
                n_ent.delete(0, "end")
                n_ent.insert(0, new)

    def _on_apply(self):
        def _do():
            self._sync_params_to_state()
            self.state.save_user_params()
            self.state.apply_lens_params_to_schema()
            if self._on_apply_callback:
                self._on_apply_callback()
            self._status.set("参数已应用")
            messagebox.showinfo("应用完成", "当前参数已保存并应用到流程卡片。")
        self._with_busy(_do)

    def _sync_params_to_state(self):
        e = self._entries
        _TYPE_MAP = {"str": str, "float": float, "int": int}
        kwargs = {}
        for section in SCHEMA["gui_sections"]:
            for f in section["fields"]:
                if "attr" not in f:
                    continue
                widget = e[f["attr"]]
                if isinstance(widget, tk.Text):
                    raw = widget.get("1.0", "end-1c").strip()
                else:
                    raw = widget.get().strip()
                converter = _TYPE_MAP.get(f["type"], str)
                # 空字符串时使用 schema 中的默认值，避免 float("") 报错
                if raw == "" and "default" in f:
                    raw = str(f["default"])
                kwargs[f["attr"]] = converter(raw)
        self.state.update_lens_params(**kwargs)
        self._params = self.state.lens_params

    def _on_calculate(self):
        def _do():
            self._sync_params_to_state()
            result = calculate(self._params)
            self._last_result = result
            self._display_result(result)
            self._status.set(f"计算完成 — 焦距={result.focal_length}mm")
        self._with_busy(_do)

    def _display_result(self, r: CalcResult):
        t = self._result
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.tag_configure("hdr", foreground=CLR_ACCENT, font=(FONT, 11, "bold"))
        t.configure(tabs=("140p", "300p"))

        def _rz(text: str) -> str:
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text

        def _h(text):
            t.insert("end", f"\n{'=' * 45}\n{text}\n{'=' * 45}\n", "hdr")
        def _l(label, value, unit=""):
            t.insert("end", f"{label}\t{_rz(value)}\t{unit}\n")

        _h("基本光学参数")
        _l("焦距 f", f"{r.focal_length:.4f}", "mm")
        _l("后焦距 S1", f"{r.back_focal_s1:.4f}", "mm")
        _l("后焦距 S2", f"{r.back_focal_s2:.4f}", "mm")
        _h("下料 / 毛坯尺寸")
        _l("毛坯口径", f"{r.blank_diameter:.2f}", "mm")
        _l("下料中心厚度", f"{r.blank_thickness:.3f}", "mm")
        _h("去除量拆分")
        _l("S1 精磨量", f"{r.grinding_s1:.2f}", "mm")
        _l("S1 抛光量", f"{r.polishing_s1:.2f}", "mm")
        _l("S2 精磨量", f"{r.grinding_s2:.2f}", "mm")
        _l("S2 抛光量", f"{r.polishing_s2:.2f}", "mm")
        _h("工序中厚")
        _l("铣磨S1后 Tc", f"{r.tc_after_mill_s1:.3f}", "mm")
        _l("铣磨S2后 Tc", f"{r.tc_after_mill_s2:.3f}", "mm")
        _l("精抛S1后 Tc (产品)", f"{r.tc_after_grinding_s1:.3f}", "mm")
        _l("精抛S2后 Tc (校验)", f"{r.tc_after_grinding_s2:.3f}", "mm")
        for side, label in (("s1", "S1"), ("s2", "S2")):
            _h(f"矢高 {label}")
            _l("标准矢高", f"{getattr(r, f'sag_{side}'):.6f}", "mm")
            _l("最大矢高差", f"{getattr(r, f'sag_diff_{side}'):.6f}", "mm")
            _l("最大矢高", f"{getattr(r, f'sag_max_{side}'):.6f}", "mm")
            _l("R最大值(矢高反推)", f"{getattr(r, f'r_max_{side}'):.4f}", "mm")
        for side, label in (("r1", "R1"), ("r2", "R2")):
            _h(f"{label} 曲率半径公差")
            rv = abs(getattr(self._params, side))
            unit = "\u00b5m" if rv < 35 else "%"
            _l("A级样板精度", f"{getattr(r, f'{side}_sample_precision'):.4f}", unit)
            _l("\u0394R(含样板)", f"{getattr(r, f'{side}_dr_with_sample'):.4f}", "mm")
            _l("\u0394R(不含样板)", f"{getattr(r, f'{side}_dr_no_sample'):.4f}", "mm")
            _l("R值上限", f"{getattr(r, f'{side}_upper'):.4f}", "mm")
            _l("R值下限", f"{getattr(r, f'{side}_lower'):.4f}", "mm")
            _l("实际上/下限",
               f"{getattr(r, f'{side}_actual_upper')} / {getattr(r, f'{side}_actual_lower')}")
        for s in ("s1", "s2"):
            _h(f"偏心 / 面倾斜 ({s.upper()})")
            _l("面倾斜@0.008mm偏心", f"{getattr(r, f'tilt_{s}_per_mm'):.2f}", "'")
            _l("偏心差@1'面倾斜", f"{getattr(r, f'decent_{s}_per_tilt'):.5f}", "mm")
            _l("球心距@1'面倾斜", f"{getattr(r, f'sphere_center_{s}'):.4f}", "mm")
            _l("反射球心距", f"{getattr(r, f'reflect_center_{s}'):.6f}", "mm")
        _l("边厚差@0.004mm偏心", f"{r.edge_thick_diff_s1:.4f}", "mm")
        _h("面倾斜 (球心距反算)")
        _l("S1 面倾斜X", f"{r.tilt_from_center_s1:.2f}", "'")
        _l("S2 面倾斜X", f"{r.tilt_from_center_s2:.2f}", "'")
        t.configure(state="disabled")

    def _show_calculation_process(self):
        if not _HAS_MPL:
            messagebox.showerror("错误", "需要 matplotlib 来渲染公式。")
            return
        import matplotlib
        matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        matplotlib.rcParams['axes.unicode_minus'] = False
        p = self._params
        r = self._last_result
        if r is None:
            messagebox.showinfo("提示", "请先点击「开始计算」。")
            return
        win = tk.Toplevel(self.root)
        win.title("计算过程详细推导")
        win.geometry("860x720")
        win.configure(bg=CLR_PAPER)
        canvas = tk.Canvas(win, bg=CLR_PAPER, highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        panel = tk.Frame(canvas, bg=CLR_PAPER)
        panel.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=panel, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        panel.bind("<MouseWheel>", _on_mousewheel)

        def _step(title, formula, result_text, note=""):
            frm = tk.Frame(panel, bg=CLR_PANEL,
                           highlightbackground=CLR_BORDER, highlightthickness=1)
            frm.pack(fill="x", padx=12, pady=6)
            tk.Label(frm, text=title, font=(FONT, 11, "bold"),
                     fg=CLR_ACCENT, bg=CLR_PANEL, anchor="w"
                     ).pack(fill="x", padx=12, pady=(8, 2))
            if note:
                tk.Label(frm, text=note, font=(FONT, 9, "italic"),
                         fg=CLR_SUBTEXT, bg=CLR_PANEL, anchor="w",
                         justify="left").pack(fill="x", padx=12, pady=(0, 2))
            fig = Figure(figsize=(7.5, 0.45), dpi=120)
            fig.patch.set_alpha(0)
            fig.text(0.5, 0.5, f"${formula}$", fontsize=13,
                     ha="center", va="center")
            mpl_canvas = FigureCanvasTkAgg(fig, master=frm)
            mpl_canvas.draw()
            mpl_canvas.get_tk_widget().pack(fill="x", padx=12, pady=4)
            tk.Label(frm, text=result_text, font=(FONT, 9),
                     fg=CLR_TEXT, bg=CLR_PANEL, anchor="w",
                     justify="left", wraplength=800
                     ).pack(fill="x", padx=12, pady=(0, 8))

        ca1 = min(p.s1_ca, p.diameter)
        ca2 = min(p.s2_ca, p.diameter)
        term1 = (p.n - 1) * (1.0 / p.r1 - 1.0 / (-p.r2))
        term2 = (p.n - 1) ** 2 * p.tc / (p.n * p.r1 * (-p.r2))
        _step("1. 焦距计算（透镜制造者公式）",
              r"\frac{1}{f} = (n-1)\left(\frac{1}{R_1} - \frac{1}{R_2}\right)"
              r" + \frac{(n-1)^2 T_c}{n R_1 (-R_2)}",
              f"代入值:  n={p.n},  R₁={p.r1} mm,  R₂={p.r2} mm,  Tc={p.tc} mm\n"
              f"  term₁ = ({p.n}-1)×(1/{p.r1} − 1/{-p.r2}) = {term1:.6f}\n"
              f"  term₂ = ({p.n}-1)²×{p.tc} / ({p.n}×{p.r1}×{-p.r2}) = {term2:.10f}\n"
              f"  焦距 f = 1 / ({term1:.6f} + {term2:.10f}) = {r.focal_length:.4f} mm")
        bfl1_arg = p.tc * (p.n - 1) / (p.n * p.r1)
        bfl2_arg = p.tc * (p.n - 1) / (p.n * (-p.r2))
        _step("2. 后焦距 BFL",
              r"\text{BFL}_{S1} = f\left(1 - \frac{T_c (n-1)}{n R_1}\right)\qquad"
              r"\text{BFL}_{S2} = f\left(1 - \frac{T_c (n-1)}{n (-R_2)}\right)",
              f"  BFL_S1 = {r.focal_length:.4f} × (1 − {bfl1_arg:.6f}) = {r.back_focal_s1:.2f} mm\n"
              f"  BFL_S2 = {r.focal_length:.4f} × (1 − {bfl2_arg:.6f}) = {r.back_focal_s2:.2f} mm")


# ──────────────────────────────────────────────
# 启动入口
# ──────────────────────────────────────────────

def main():
    """启动 Process Card 流程管理系统。
    
    数据默认加载 manufacturing_process.json，
    编辑后需点击「保存」或按 Ctrl+S 持久化到 JSON 文件。
    """
    root = tk.Tk()
    TaskApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
