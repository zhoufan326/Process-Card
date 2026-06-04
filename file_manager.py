"""JSON 项目文件管理组件。

提供 FileManager 类，封装 JSON 文件的扫描、加载、保存为、
浏览选择等交互逻辑。通过回调委托实际的数据加载/保存操作。

用法:
    mgr = FileManager(
        parent,
        script_dir=os.path.dirname(__file__),
        on_load=lambda path: load_preset(path),
        on_save=lambda path: save_preset(path),
        set_status=app._set_status,
    )
    # 在需要刷新列表时调用:
    mgr.refresh_file_list()
"""

import os
import glob
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional


class FileManager(ttk.Frame):
    """管理项目 JSON 文件的加载、保存与列表。

    是一个可嵌入的 ttk.Frame，自动绑定 Combobox 下拉文件和
    三个操作按钮（加载 / 保存为 / 浏览）。

    注意:
        field_schema.json 被保护，不会出现在下拉框中，
        也无法通过「保存为」覆盖，防止误操作。
    """

    def __init__(
        self,
        parent,
        *,
        script_dir: str = "",
        on_load: Optional[Callable[[str], None]] = None,
        on_save: Optional[Callable[[str], None]] = None,
        set_status: Optional[Callable[[str], None]] = None,
        bg: str = "#F5F0E8",
    ):
        """
        参数:
            parent: tk 父容器
            script_dir: 扫描 .json 文件的目录
            on_load: 加载回调, 接收文件路径, 返回 None
            on_save: 保存回调, 接收文件路径, 返回 None
            set_status: 状态栏回调
            bg: 背景色
        """
        super().__init__(parent, style="File.TFrame")
        self._script_dir = script_dir
        self._on_load = on_load
        self._on_save = on_save
        self._set_status = set_status
        self.current_file: str | None = None
        self._protected_files = {"field_schema.json"}
        self._build(bg)

    # ── 控件构建 ──────────────────────────────

    def _build(self, bg: str):
        self.grid_columnconfigure(1, weight=1)

        tk.Label(
            self, text=chr(0x25A0) + " 项目文件",
            anchor="w",
            bg=bg, fg="#5D4037",
            font=("Microsoft YaHei", 9, "bold"),
        ).grid(row=0, column=0, padx=(0, 8))

        self._combo = ttk.Combobox(self, state="readonly", width=28, font=("Microsoft YaHei", 9))
        self._combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))

        tk.Button(
            self, text="加载", width=6, font=("Microsoft YaHei", 9),
            command=self._on_load_from_combo,
            bg="#8D6E63", fg="white", relief="flat", cursor="hand2",
            activebackground="#6D4C41", activeforeground="white",
        ).grid(row=0, column=2, padx=2)

        tk.Button(
            self, text="保存为", width=6, font=("Microsoft YaHei", 9),
            command=self._on_save_as,
            bg="#A1887F", fg="white", relief="flat", cursor="hand2",
            activebackground="#795548", activeforeground="white",
        ).grid(row=0, column=3, padx=2)

        tk.Button(
            self, text="浏览", width=6, font=("Microsoft YaHei", 9),
            command=self._on_load_preset,
            bg="#D7CCC8", fg="#5D4037", relief="flat", cursor="hand2",
            activebackground="#BCAAA4", activeforeground="#3E2723",
        ).grid(row=0, column=4, padx=2)

    # ── 公有方法 ───────────────────────────────

    def refresh_file_list(self):
        """扫描 script_dir 下所有 .json 并填充到 Combobox（排除受保护文件）。"""
        pattern = os.path.join(self._script_dir, "*.json")
        files = sorted(glob.glob(pattern))
        names = [os.path.basename(f) for f in files
                 if os.path.basename(f) not in self._protected_files]
        self._combo["values"] = names
        if names:
            self._combo.set(names[0])

    def get_selected(self) -> str:
        """返回下拉框中当前选中的文件名。"""
        return self._combo.get()

    def set_selected(self, name: str):
        """设置下拉框为指定文件名。"""
        self._combo.set(name)

    # ── 事件处理 ───────────────────────────────

    def _on_load_from_combo(self):
        name = self._combo.get()
        if not name:
            return
        path = os.path.join(self._script_dir, name)
        self._invoke_load(path)

    def _on_save_as(self):
        path = filedialog.asksaveasfilename(
            title="保存项目文件",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=self._script_dir,
        )
        if not path:
            return
        name = os.path.basename(path)
        # 阻止覆盖受保护文件
        if name in self._protected_files:
            messagebox.showwarning(
                "文件受保护",
                f"{name} 是系统配置文件，不能通过「保存为」覆盖。")
            return
        if self._on_save:
            self._on_save(path)
        self.current_file = path
        self.refresh_file_list()
        self._combo.set(name)
        if self._set_status:
            self._set_status(f"已保存至 {name}")

    def _on_load_preset(self):
        path = filedialog.askopenfilename(
            title="选择 JSON 文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=self._script_dir,
        )
        if not path:
            return
        self._invoke_load(path)

    def _invoke_load(self, path: str):
        name = os.path.basename(path)
        if name in self._protected_files:
            messagebox.showwarning(
                "文件受保护",
                f"{name} 是系统配置文件，不能作为项目文件加载。")
            return
        try:
            if self._on_load:
                self._on_load(path)
            self.current_file = path
            self.refresh_file_list()
            self._combo.set(name)
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
