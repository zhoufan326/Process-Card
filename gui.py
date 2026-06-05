r"""Process Card — 流程卡片管理系统。
中式古典简约风格界面。

布局:
┌────────────────────────────────────────────┐
│  ■ Process Card    流程卡片                │
├────────────────────────────────────────────┤
│  ■ 项目文件  [preset.json ▾] [加载][保存][浏览] │
├──────────────┬─────────────────────────────┤
│  表单区       │                             │
│  车间/名称/  │      Treeview 主数据区       │
│  对象/要求   │                             │
│  [保存][新建]│                             │
│  [+要求][删除]│                            │
│  [导出Excel] │                             │
├──────────────┴─────────────────────────────┤
│  ■ 就绪                                    │
└────────────────────────────────────────────┘
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from set import TaskGroup, Tasks, load_preset, save_preset
from tree_drag_controller import TreeDragController
from file_manager import FileManager

# ──────────────────────────────────────────────
# 中式古典配色
# ──────────────────────────────────────────────

CLR_PAPER = "#F5F0E8"     # 宣纸底色 – 全局背景
CLR_PANEL = "#FDF8F2"     # 面板底色 – 稍浅
CLR_HEADER = "#E8D5B7"    # 标题栏 – 暖沙色
CLR_BORDER = "#D3C1AD"    # 分隔线 – 淡茶色
CLR_TEXT = "#3E2723"      # 正文 – 深墨色
CLR_SUBTEXT = "#5D4037"   # 辅助文字 – 焦茶色
CLR_ACCENT = "#8D6E63"    # 按钮主色 – 驼棕色
CLR_ACCENT_HI = "#6D4C41" # 按钮悬停 – 深棕
CLR_SECOND = "#A1887F"    # 按钮次色
CLR_LIGHT = "#D7CCC8"     # 按钮浅色
CLR_TREE_GROUP = "#EDE0D4"  # Treeview 组行 – 浅砂
CLR_TREE_REQ = "#FDF8F2"    # Treeview 子行 – 米白
CLR_TREE_SEL = "#D4E6C3"    # 选中行 – 青瓷绿

TAG_GROUP = "group"
TAG_REQ = "req"
PAD_X = 12
PAD_Y = 4
FONT = "Microsoft YaHei"


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _btn(parent, text, command, *, color=CLR_ACCENT, fg="white", width=9, **kw):
    """创建风格统一的按钮。"""
    return tk.Button(
        parent, text=text, command=command, width=width,
        font=(FONT, 9), bg=color, fg=fg,
        relief="flat", cursor="hand2", bd=0,
        activebackground=CLR_ACCENT_HI, activeforeground="white",
        **kw,
    )


def _sep(parent, row, colspan=2, pady=6):
    """横向分隔线。"""
    s = tk.Frame(parent, height=1, bg=CLR_BORDER)
    s.grid(row=row, column=0, columnspan=colspan, sticky="ew", padx=PAD_X, pady=pady)
    s.grid_propagate(False)


# ──────────────────────────────────────────────
# 主应用
# ──────────────────────────────────────────────

class TaskApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._edit_group_idx: int | None = None
        self._edit_req_idx: int = -1
        self._dirty = False

        self._init_style()
        self._build_body()
        self._build_footer()
        self._init_drag_ctrl()
        self._bind_events()
        self._file_mgr.refresh_file_list()
        self._refresh_tree()
        self.bay_entry.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ── 全局样式 ──────────────────────────────

    def _init_style(self):
        self.root.configure(bg=CLR_PAPER)
        self.root.title("Process Card · 流程管理")
        self.root.geometry("1200x700")
        self.root.minsize(960, 560)
        self.root.resizable(True, True)
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
        h = tk.Frame(self.root, bg=CLR_HEADER, height=36)
        h.grid(row=0, column=0, columnspan=2, sticky="ew")
        h.grid_propagate(False)
        tk.Label(
            h, text=chr(0x25A0) + "  Process Card  —  流程卡片管理",
            font=(FONT, 12, "bold"), fg=CLR_TEXT, bg=CLR_HEADER,
        ).pack(side="left", padx=14, pady=6)

    # ── 主体区域 ──────────────────────────────

    def _build_body(self):
        # — 左侧面板（标题 + 文件栏 + 表单 + 按钮） —
        left = tk.Frame(self.root, bg=CLR_PAPER, width=280)
        left.grid(row=0, column=0, sticky="nswe", padx=(PAD_X, 0), pady=PAD_Y)
        left.grid_propagate(False)

        # 子标题
        tk.Label(left, text="\u25a0 工序编辑",
                 font=(FONT, 11, "bold"), fg=CLR_TEXT, bg=CLR_HEADER,
                 anchor="w", padx=14).pack(fill="x", ipady=6)

        # 文件管理栏嵌入
        fb = tk.Frame(left, bg=CLR_PAPER)
        fb.pack(fill="x", pady=(6, 0))
        self._file_mgr = FileManager(
            fb,
            script_dir=os.path.dirname(os.path.abspath(__file__)),
            on_load=self._do_load,
            on_save=self._do_save,
            set_status=self._set_status,
            bg=CLR_PAPER,
        )
        self._file_mgr.pack(fill="x", expand=True)

        # 表单面板
        form_box = tk.Frame(left, bg=CLR_PANEL, bd=0,
                            highlightbackground=CLR_BORDER, highlightthickness=1)
        form_box.pack(fill="x", pady=(8, 0), padx=0)
        self._build_form(form_box)
        _sep(form_box, 7, colspan=2, pady=4)
        self._build_buttons(form_box)

        # ── 详情 Text 区（选中要求后在此显示完整内容，自动换行） ──
        detail_frame = tk.Frame(left, bg="white",
                                highlightbackground=CLR_BORDER, highlightthickness=1)
        detail_frame.pack(fill="x", pady=(6, 0))
        detail_frame.grid_columnconfigure(0, weight=1)

        self.detail_text = tk.Text(
            detail_frame, font=(FONT, 9), bg="#FAFAFA", fg=CLR_TEXT,
            wrap="word", state="disabled", height=5, padx=6, pady=4,
            relief="flat",
        )
        self.detail_text.grid(row=0, column=0, sticky="nswe", padx=4, pady=4)

        # 占位提示（与 detail_text 重叠，选中后隐藏）
        self._detail_placeholder = tk.Label(
            detail_frame, text="点击要求行查看详情（自动换行）",
            font=(FONT, 9), fg="#BDBDBD", bg="#FAFAFA", anchor="nw", padx=10, pady=6,
        )
        self._detail_placeholder.grid(row=0, column=0, sticky="nw", padx=4, pady=4)

        # — 右侧展示面板 —
        right = tk.Frame(self.root, bg=CLR_PAPER)
        right.grid(row=0, column=1, sticky="nswe", padx=PAD_X, pady=PAD_Y)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        tk.Label(right, text="\u25a0 流程工序",
                 font=(FONT, 11, "bold"), fg=CLR_TEXT, bg=CLR_HEADER,
                 anchor="w", padx=14).grid(row=0, column=0, sticky="ew", ipady=6)

        # ── Treeview 区域 ──
        tv_box = tk.Frame(right, bg="white",
                          highlightbackground=CLR_BORDER, highlightthickness=1)
        tv_box.grid(row=1, column=0, sticky="nswe", pady=(6, 0))
        tv_box.grid_rowconfigure(0, weight=1)
        tv_box.grid_columnconfigure(3, weight=1)  # require 列随窗口伸缩

        columns = ("bay", "process", "obj", "require")
        self.tree = ttk.Treeview(tv_box, columns=columns, show="tree headings", height=20)
        self.tree.heading("#0", text="")
        self.tree.heading("bay", text="车间")
        self.tree.heading("process", text="工序")
        self.tree.heading("obj", text="对象")
        self.tree.heading("require", text="要求")
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("bay", width=60, anchor="center", stretch=False)
        self.tree.column("process", width=90, stretch=False)
        self.tree.column("obj", width=50, anchor="center", stretch=False)
        self.tree.column("require", width=300, minwidth=150, stretch=True)
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nswe", padx=2, pady=2)

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
                bg="white", fg=CLR_TEXT, relief="solid", bd=1,
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
            bg="white", fg=CLR_TEXT, relief="solid", bd=1,
            wrap="word", insertbackground=CLR_ACCENT,
        )
        self.req_text.grid(row=3, column=1, columnspan=2, sticky="ew", pady=PAD_Y)
        frm.grid_columnconfigure(2, weight=1)

    def _build_buttons(self, parent):
        """按钮组。"""
        bf = tk.Frame(parent, bg=CLR_PANEL)
        bf.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 10))

        _btn(bf, "新建组", self._on_new, color=CLR_SECOND, width=9).grid(row=0, column=0, padx=2, pady=2)
        _btn(bf, "+ 要求", self._on_add_req, color=CLR_LIGHT, fg=CLR_SUBTEXT, width=9).grid(row=0, column=1, padx=2, pady=2)
        _btn(bf, "删 除", self._on_delete, color=CLR_LIGHT, fg=CLR_SUBTEXT, width=9).grid(row=1, column=1, padx=2, pady=2)

        _btn(bf, "导出工艺卡", self._on_export, color=CLR_HEADER, fg=CLR_TEXT, width=20).grid(
            row=2, column=0, columnspan=2, padx=2, pady=(6, 2), sticky="ew"
        )
        _btn(bf, "工艺计算", self._on_process_calc, color=CLR_ACCENT, fg="white", width=20).grid(
            row=3, column=0, columnspan=2, padx=2, pady=2, sticky="ew"
        )

    # ── 底部状态栏 ────────────────────────────

    def _build_footer(self):
        ft = tk.Frame(self.root, bg=CLR_HEADER, height=28)
        ft.grid(row=1, column=0, columnspan=2, sticky="ew")
        ft.grid_propagate(False)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(
            ft, textvariable=self.status_var, anchor="w",
            font=(FONT, 9), fg=CLR_SUBTEXT, bg=CLR_HEADER,
        ).pack(side="left", padx=14, pady=4)

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

    # ── 状态反馈 ──────────────────────────────

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    # ── 脏标记 ────────────────────────────────

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.root.title("Process Card · 流程管理 *")

    def _clear_dirty(self):
        self._dirty = False
        self.root.title("Process Card · 流程管理")

    def _on_closing(self):
        if self._dirty:
            ans = messagebox.askyesnocancel("未保存的更改",
                "文件已修改，是否保存？\n\n\"是\" = 保存并退出\n\"否\" = 不保存直接退出\n\"取消\" = 返回程序")
            if ans is None:
                return
            if ans:
                if self._file_mgr and self._file_mgr.current_file:
                    save_preset(self._file_mgr.current_file)
                else:
                    self._file_mgr._on_save_as()
        self.root.destroy()

    # ── 文件管理回调 ──────────────────────────

    def _do_load(self, path: str):
        """FileManager 的加载回调：清空状态，加载并刷新。"""
        self._edit_group_idx = None
        self._edit_req_idx = -1
        self._clear_inputs()
        load_preset(path)
        self._refresh_tree()
        self._clear_dirty()
        name = os.path.basename(path)
        self._set_status(f"已加载 {len(Tasks)} 组（{name}）")

    def _do_save(self, path: str):
        """FileManager 的保存回调：将 Tasks 写入文件。"""
        save_preset(path)
        self._clear_dirty()

    # ── 输入框操作 ────────────────────────────

    def _fill_inputs(self, bay="", process="", obj="", req=""):
        for ent, val in [
            (self.bay_entry, bay), (self.process_entry, process),
            (self.obj_entry, obj),
        ]:
            ent.delete(0, tk.END)
            ent.insert(0, val)
        self.req_text.delete("1.0", tk.END)
        self.req_text.insert("1.0", req)

    def _clear_inputs(self):
        self._fill_inputs()

    def _get_req_text(self) -> str:
        return self.req_text.get("1.0", "end-1c").strip()

    # ── 实时同步：表单 → Tasks → Treeview ────

    def _on_root_click(self, event=None):
        """点击 GUI 任意位置时同步表单内容到 Tasks。"""
        if self._edit_group_idx is not None:
            self._mark_dirty()
            self._apply_form_to_tasks()

    def _apply_form_to_tasks(self):
        if self._edit_group_idx is None:
            return
        bay = self.bay_entry.get().strip()
        process = self.process_entry.get().strip()
        obj = self.obj_entry.get().strip()
        req = self._get_req_text()

        g = Tasks[self._edit_group_idx]
        g.bay, g.process, g.obj = bay, process, obj
        if self._edit_req_idx >= 0:
            if req:
                g.requires[self._edit_req_idx] = req

        sel = self.tree.selection()
        self._refresh_tree()
        if sel:
            for s in sel:
                if self.tree.exists(s):
                    self.tree.selection_set(s)
                    self.tree.focus(s)
                    break

    # ── 占位符解析（可失效缓存） ────────────────

    _ctx_cache = None

    @classmethod
    def _invalidate_ctx_cache(cls):
        cls._ctx_cache = None
        import lens_calc  # ensure module is loaded
        import importlib, sys
        importlib.reload(sys.modules["lens_calc"])

    @classmethod
    def _resolve_placeholders(cls, req: str) -> str:
        """将 ${xxx} 占位符替换为 field_schema.json 默认值。"""
        import json
        from lens_calc import LensParams, calculate

        if cls._ctx_cache is None:
            p = LensParams()
            r = calculate(p)
            sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_schema.json")
            with open(sp, "r", encoding="utf-8") as f:
                schema = json.load(f)
            ctx = {}
            for item in schema["export_ctx"]:
                if "ctx" not in item:
                    continue
                src = p if item["source"] == "params" else r
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
            cls._ctx_cache = ctx

        result = req
        for k, v in cls._ctx_cache.items():
            result = result.replace(k, v)
        return result

    # ── 组拖拽 ────────────────────────────────

    def _on_move_group(self, src: int, tgt: int):
        group = Tasks.pop(src)
        Tasks.insert(tgt, group)
        if self._edit_group_idx is not None:
            if self._edit_group_idx == src:
                self._edit_group_idx = tgt
            elif self._edit_group_idx == tgt:
                self._edit_group_idx = src
        self._mark_dirty()
        self._refresh_tree()
        self._set_status(f"已移动组 [{tgt + 1}] {group.process}")

    def _on_move_req(self, gi: int, src: int, tgt: int):
        """组内 req 重排。"""
        req = Tasks[gi].requires.pop(src)
        Tasks[gi].requires.insert(tgt, req)
        if self._edit_group_idx == gi and self._edit_req_idx >= 0:
            if self._edit_req_idx == src:
                self._edit_req_idx = tgt
            elif self._edit_req_idx == tgt:
                self._edit_req_idx = src
        self._mark_dirty()
        self._refresh_tree()
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
        for gi, g in enumerate(Tasks):
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
        for gi, g in enumerate(Tasks):
            gid = self._group_item_id(gi)
            tree.insert(
                "", "end", iid=gid,
                values=(g.bay, g.process, g.obj, f"\u25a0 {len(g.requires)} \u9879"),
                tags=(TAG_GROUP,),
            )
            for ri, req in enumerate(g.requires):
                tree.insert(
                    gid, "end", iid=self._req_item_id(gi, ri),
                    values=("", "", "", self._resolve_placeholders(req)),
                    tags=(TAG_REQ,),
                )
        for item in tree.get_children():
            tree.item(item, open=True)

    # ── 选择与编辑 ────────────────────────────

    def _show_detail(self, text: str):
        """在底部详情区显示完整文本（自动换行）。"""
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")
        # 隐藏占位提示
        self._detail_placeholder.grid_remove()

    def _clear_detail(self):
        """清空详情区，回到占位提示。"""
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.configure(state="disabled")
        self._detail_placeholder.grid()

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
        g = Tasks[gi]
        if ri == -1:
            self._edit_group_idx = gi
            self._edit_req_idx = -1
            self._fill_inputs(g.bay, g.process, g.obj, "")
            self._set_status(f"选中组 [{gi + 1}] {g.process}")
        else:
            self._edit_group_idx = gi
            self._edit_req_idx = ri
            self._fill_inputs(g.bay, g.process, g.obj, g.requires[ri])
            self._set_status(f"选中 {g.process} → 要求 {ri + 1}")
            # 在底部详情区显示完整要求文本（占位符已解析）
            self._show_detail(self._resolve_placeholders(g.requires[ri]))

    def _on_tree_double(self, event=None):
        self._on_tree_select()
        self.req_text.focus_set()

    # ── 新建 / 添加 / 删除 ────────────

    def _on_new(self):
        g = TaskGroup(bay="", process="新建工序", obj="")
        Tasks.append(g)
        self._edit_group_idx = len(Tasks) - 1
        self._edit_req_idx = -1
        self._fill_inputs(g.bay, g.process, g.obj, "")
        self._mark_dirty()
        self._refresh_tree()
        self.bay_entry.focus_set()
        self._set_status("新建组模式，填写内容后自动同步")

    def _on_add_req(self):
        if self._edit_group_idx is not None:
            g = Tasks[self._edit_group_idx]
            g.requires.append("")
            self._edit_req_idx = len(g.requires) - 1
            self._fill_inputs(g.bay, g.process, g.obj, "")
            self.req_text.focus_set()
            self._mark_dirty()
            self._refresh_tree()
            self._set_status(f"已添加空要求到组 {g.process}")
        else:
            messagebox.showinfo("提示", "请先选中一个组。")

    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("删除提示", "请先选中要删除的项。")
            return
        info = self._get_group_by_item(sel[0])
        if info is None:
            return
        gi, ri = info
        if ri == -1:
            if not messagebox.askyesno("确认删除", f"确定删除组 [{gi + 1}] {Tasks[gi].process}？"):
                return
            Tasks.pop(gi)
        else:
            g = Tasks[gi]
            if not messagebox.askyesno("确认删除", f"确定删除要求「{g.requires[ri]}」？"):
                return
            g.requires.pop(ri)
        self._edit_group_idx, self._edit_req_idx = None, -1
        self._clear_inputs()
        self._mark_dirty()
        self._refresh_tree()
        self._set_status("已删除")

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
            from process_card_exporter import export_process_card
            result = export_process_card(filepath)
            messagebox.showinfo("导出完成",
                                f"工艺卡片已生成:\n{filepath}")
            self._set_status(f"工艺卡已导出")
        except PermissionError:
            messagebox.showwarning("文件被占用",
                                   "导出失败，文件正在被 Excel 或其他程序打开。\n请先关闭文件再重试。")
        except Exception as e:
            import traceback
            traceback.print_exc()   # ← 加这一行，会在终端打印完整堆栈
            messagebox.showerror("导出失败", str(e))

    def _on_process_calc(self):
        """打开工艺计算窗口。返回主窗口后将检测更新并同步。"""
        import subprocess, sys
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "process_planning.py")
        self._schema_mtime_before = os.path.getmtime(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_schema.json"))
        try:
            subprocess.Popen([sys.executable, script])
            self._set_status("已打开工艺计算窗口（关闭后将自动同步）")
            self.root.after(500, self._check_process_calc_closed)
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动工艺计算:\n{e}")

    def _check_process_calc_closed(self):
        """检测 field_schema.json mtime 变化 → 自动同步。"""
        sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_schema.json")
        try:
            mt = os.path.getmtime(sp)
        except OSError:
            self.root.after(500, self._check_process_calc_closed)
            return
        if mt == self._schema_mtime_before:
            self.root.after(500, self._check_process_calc_closed)
            return
        self._invalidate_ctx_cache()
        self._refresh_tree()
        self._set_status("参数已同步到显示")


# ──────────────────────────────────────────────
# 启动入口
# ──────────────────────────────────────────────

def main():
    root = tk.Tk()
    TaskApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
