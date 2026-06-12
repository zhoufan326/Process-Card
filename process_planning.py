r"""球面透镜工艺计算 — GUI 界面。

由 field_schema.json 驱动生成输入面板，
计算核心委托给 lens_calc.py。
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

os.environ.setdefault("MPLBACKEND", "TkAgg")  # 强制 TkAgg，避免打包拖入 Qt

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

import material_db
from app_state import AppState

from lens_calc import (
    LensParams, CalcResult, calculate, SCHEMA,
    _sag, _FRINGE_CONST,
)

# ═══ 配色 (共享 gui.py 中式古典风格) ═══
CLR_PAPER    = "#F5F0E8"
CLR_PANEL    = "#FDF8F2"
CLR_HEADER   = "#E8D5B7"
CLR_BORDER   = "#D3C1AD"
CLR_TEXT     = "#3E2723"
CLR_SUBTEXT  = "#5D4037"
CLR_ACCENT   = "#8D6E63"
CLR_ACCENT_HI = "#6D4C41"
FONT = "Microsoft YaHei"


# ═══ GUI ═══

class ProcessPlanApp:
    """球面透镜工艺计算 GUI。"""

    def __init__(self, root: tk.Tk | tk.Toplevel, app_state: AppState | None = None):
        self.root = root
        self.state = app_state or AppState()
        self._params = self.state.lens_params
        self._material_dict, self._material_list = material_db.load_materials()
        self._last_result = None
        self._destroyed = False
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
        left = tk.Frame(parent, bg=CLR_PANEL, highlightbackground=CLR_BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=False, padx=(0, 4))

        canvas = tk.Canvas(left, bg=CLR_PANEL, width=420, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        panel = tk.Frame(canvas, bg=CLR_PANEL)
        panel.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=panel, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # 鼠标在 canvas 区域内时滚轮滚动（离开自动解绑，避免关闭窗口后残留回调）
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda e2: self._on_canvas_scroll(e2, canvas)))
        canvas.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))
        # 窗口关闭时确保清理全局绑定
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._build_input_fields(panel)

    def _on_canvas_scroll(self, event, canvas):
        """Canvas 滚轮滚动，带控件销毁保护。"""
        if self._destroyed:
            return
        try:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def _build_result_panel(self, parent):
        right = tk.Frame(parent, bg=CLR_PANEL, highlightbackground=CLR_BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        self._result = tk.Text(right, font=("Consolas", 11), bg="#FAFAFA",
                               fg=CLR_TEXT, wrap="word", state="disabled", padx=10, pady=10)
        self._result.pack(fill="both", expand=True, padx=2, pady=2)

    def _build_footer(self, root):
        bf = tk.Frame(root, bg=CLR_HEADER, height=40)
        bf.pack(fill="x")
        bf.pack_propagate(False)
        btn_kw = dict(font=(FONT, 10, "bold"), bg=CLR_ACCENT, fg="white",
                      relief="flat", cursor="hand2", bd=0,
                      activebackground=CLR_ACCENT_HI, activeforeground="white")
        tk.Button(bf, text="开始计算", command=self._on_calculate,
                  **btn_kw, width=12).pack(side="left", padx=14, pady=5)
        tk.Button(bf, text="应用", command=self._on_apply,
                  **btn_kw, width=12).pack(side="left", padx=4, pady=5)
        tk.Button(bf, text="展示计算过程", command=self._show_calculation_process,
                  **btn_kw, width=14).pack(side="left", padx=4, pady=5)
        self._status = tk.StringVar(value="就绪 — 请输入参数后点击「开始计算」")
        tk.Label(bf, textvariable=self._status, font=(FONT, 9),
                 fg=CLR_SUBTEXT, bg=CLR_HEADER, anchor="e").pack(side="right", padx=16, pady=5)

    def _on_closing(self):
        """关闭窗口时清理全局绑定并释放 grab。"""
        self._destroyed = True
        try:
            self.root.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        try:
            self.root.grab_release()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ═══════════════════════════════════════════════
    #  Schema-Driven 输入面板构建
    #  核心思想：字段定义在 field_schema.json 中，Python 代码只负责渲染
    #  优点：新增字段只需改 JSON，不改代码；UI 和逻辑解耦
    # ═══════════════════════════════════════════════

    def _build_input_fields(self, panel):
        """由 field_schema.json 驱动，自动生成全部输入控件。"""
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
                ent.mark_set("insert", "1.0")  # 光标移到开头
            elif attr == "material":
                ent = ttk.Combobox(frm, values=self._material_list,
                                   font=(FONT, 9), width=18)
                ent.pack(side="left")
                if default in self._material_dict:
                    ent.set(default)
                else:
                    ent.set(default)
                ent.bind("<<ComboboxSelected>>", self._on_material_changed)
                ent.bind("<KeyRelease>", self._on_material_changed)
            else:
                ent = tk.Entry(frm, font=(FONT, 9), width=18, bg="white",
                               fg=CLR_TEXT, relief="solid", bd=1)
                ent.pack(side="left")
                ent.insert(0, default)
                ent.icursor(0)  # 光标移到开头

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

        # ── 上下键快速切换输入框（排除 Combobox，避免与下拉菜单冲突） ──
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
            """delta=+1 向下, delta=-1 向上，带控件销毁保护。"""
            if self._destroyed:
                return
            try:
                focused = self.root.focus_get()
            except tk.TclError:
                return
            for i, w in enumerate(self._entry_order):
                if w == focused:
                    target = (i + delta) % len(self._entry_order)
                    try:
                        self._entry_order[target].focus_set()
                    except tk.TclError:
                        pass
                    return
            # 无焦点时默认聚焦第一个
            try:
                self._entry_order[0].focus_set()
            except tk.TclError:
                pass

        for w in self._entry_order:
            w.bind("<Down>", lambda e, d=+1: _nav(d), add="+")
            w.bind("<Up>", lambda e, d=-1: _nav(d), add="+")

        # 初始同步：默认材料 → 折射率
        self._on_material_changed()

    # ── 材料联动 ──

    def _on_material_changed(self, event=None):
        """材料下拉选择或手动输入后，自动查询并填入折射率 n。"""
        if self._destroyed:
            return
        if "material" not in self._entries or "n" not in self._entries:
            return
        try:
            name = self._entries["material"].get().strip()
        except tk.TclError:
            return
        n_val = self._material_dict.get(name)
        if n_val is not None and n_val > 0:
            n_ent = self._entries["n"]
            try:
                old = n_ent.get().strip()
                new = str(n_val)
                if old != new:
                    n_ent.delete(0, "end")
                    n_ent.insert(0, new)
            except tk.TclError:
                pass

    # ═══════════════════════════════════════════════
    #  应用按钮 → 永久保存到 field_schema.json
    # ═══════════════════════════════════════════════

    def _on_apply(self, silent=False):
        """将当前输入值永久保存到 field_schema.json 和 user_params.json。"""
        self._sync_params_to_state()
        self.state.save_user_params()
        # 同步到 field_schema.json（写入 default 字段）
        import json, time
        from lens_calc import _write_root
        schema_path = os.path.join(_write_root(), "field_schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        else:
            p = self.state.lens_params
            for section in schema.get("gui_sections", []):
                for f in section.get("fields", []):
                    if "attr" in f:
                        val = getattr(p, f["attr"], None)
                        if val is not None:
                            f["default"] = val
            for attempt in range(3):
                try:
                    with open(schema_path, "w", encoding="utf-8") as f:
                        json.dump(schema, f, ensure_ascii=False, indent=2)
                    break
                except OSError:
                    if attempt < 2:
                        time.sleep(0.5)
                    continue
        if not silent:
            messagebox.showinfo("应用完成", "当前参数已永久保存到 field_schema.json。")
        self._status.set("参数已应用")

    # ── 校验 & 计算 ──

    def _validate(self, e: dict) -> str | None:
        """输入校验，返回错误信息或 None。"""
        try:
            r1 = float(e["r1"].get())
            r2 = float(e["r2"].get())
            n = float(e["n"].get())
            dia = float(e["diameter"].get())
            ca1 = float(e["s1_ca"].get())
            ca2 = float(e["s2_ca"].get())
            tc = float(e["tc"].get())
        except ValueError:
            return "存在非数字输入，请检查所有数值字段。"

        if r1 == 0 or r2 == 0:
            return "曲率半径 R1 和 R2 不能为零。"
        if not (n >= 1.0):
            return "折射率 n 必须大于等于 1.0。"
        if tc <= 0:
            return "中心厚度 Tc 必须大于 0。"
        if ca1 > dia:
            return f"S1 CA ({ca1}) 不能大于外径 ({dia})。"
        if ca2 > dia:
            return f"S2 CA ({ca2}) 不能大于外径 ({dia})。"
        return None

    def _sync_params_to_state(self):
        """将 GUI 输入值同步到 self.state.lens_params。"""
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
                kwargs[f["attr"]] = converter(raw)
        self.state.update_lens_params(**kwargs)
        self._params = self.state.lens_params

    def _on_calculate(self):
        try:
            self._sync_params_to_state()
        except Exception as ex:
            messagebox.showerror("输入错误", f"参数读取失败:\n{ex}")
            return

        result = calculate(self._params)
        self._last_result = result
        self._display_result(result)
        self._status.set(f"计算完成 — 焦距={result.focal_length}mm")

    # ── 结果展示 ──

    def _display_result(self, r: CalcResult):
        t = self._result
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.tag_configure("hdr", foreground=CLR_ACCENT, font=(FONT, 11, "bold"))
        # 设置制表符停靠位（像素）：标签列~18字符宽，值列~36字符宽
        t.configure(tabs=("140p", "300p"))

        def _h(text):
            t.insert("end", f"\n{'=' * 45}\n{text}\n{'=' * 45}\n", "hdr")
        def _l(label, value, unit=""):
            t.insert("end", f"{label}\t{value}\t{unit}\n")

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
            _l("A级样板精度", f"{getattr(r, f'{side}_sample_precision'):.4f}", "\u00b5m")
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
        """打开新窗口，用 matplotlib 渲染 LaTeX 展示全部计算过程。"""
        if not _HAS_MPL:
            messagebox.showerror("错误",
                "需要 matplotlib 来渲染公式。\n请运行：pip install matplotlib")
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
            try:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            except tk.TclError:
                pass
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
                         justify="left"
                         ).pack(fill="x", padx=12, pady=(0, 2))

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

        # ═══════════════════════════════════════
        #  各步骤
        # ═══════════════════════════════════════

        ca1 = min(p.s1_ca, p.diameter)
        ca2 = min(p.s2_ca, p.diameter)

        term1 = (p.n - 1) * (1.0 / p.r1 - 1.0 / (-p.r2))
        term2 = (p.n - 1) ** 2 * p.tc / (p.n * p.r1 * (-p.r2))
        _step(
            "1. 焦距计算（透镜制造者公式）",
            r"\frac{1}{f} = (n-1)\left(\frac{1}{R_1} - \frac{1}{R_2}\right)"
            r" + \frac{(n-1)^2 T_c}{n R_1 (-R_2)}",
            f"代入值:  n={p.n},  R₁={p.r1} mm,  R₂={p.r2} mm,  Tc={p.tc} mm\n"
            f"  term₁ = ({p.n}-1)×(1/{p.r1} − 1/{-p.r2}) = {term1:.6f}\n"
            f"  term₂ = ({p.n}-1)²×{p.tc} / ({p.n}×{p.r1}×{-p.r2}) = {term2:.10f}\n"
            f"  焦距 f = 1 / ({term1:.6f} + {term2:.10f}) = {r.focal_length:.4f} mm"
        )

        bfl1_arg = p.tc * (p.n - 1) / (p.n * p.r1)
        bfl2_arg = p.tc * (p.n - 1) / (p.n * (-p.r2))
        _step(
            "2. 后焦距 BFL",
            r"\text{BFL}_{S1} = f\left(1 - \frac{T_c (n-1)}{n R_1}\right)\qquad"
            r"\text{BFL}_{S2} = f\left(1 - \frac{T_c (n-1)}{n (-R_2)}\right)",
            f"  BFL_S1 = {r.focal_length:.4f} × (1 − {bfl1_arg:.6f}) = {r.back_focal_s1:.2f} mm\n"
            f"  BFL_S2 = {r.focal_length:.4f} × (1 − {bfl2_arg:.6f}) = {r.back_focal_s2:.2f} mm"
        )

        sag1 = _sag(p.r1, ca1)
        sag2 = _sag(p.r2, ca2)
        _step(
            "3. 矢高计算",
            r"s = |R| - \sqrt{R^2 - \left(\frac{CA}{2}\right)^2}",
            f"  S1:  |R₁|={abs(p.r1):.4f},  CA/2={ca1/2:.1f}  →  s₁ = {sag1:.6f} mm\n"
            f"  S2:  |R₂|={abs(p.r2):.4f},  CA/2={ca2/2:.1f}  →  s₂ = {sag2:.6f} mm"
        )

        sag_per_fringe = p.wavelength * 1e-6 / _FRINGE_CONST
        _step(
            "4. 矢高差（牛顿环 · 反射式）",
            r"\Delta s = N \times \frac{\lambda}{2} \qquad"
            r"(\text{OPD}=2\Delta s,\; \Delta s=\lambda/2)",
            f"  λ = {p.wavelength} nm = {p.wavelength*1e-6:.6f} mm\n"
            f"  Δs/圈 = λ/2 = {sag_per_fringe:.6f} mm\n"
            f"  S1:  N={p.s1_n}  →  Δs₁ = {r.sag_diff_s1:.6f} mm\n"
            f"  S2:  N={p.s2_n}  →  Δs₂ = {r.sag_diff_s2:.6f} mm",
            note="反射式牛顿环: OPD=2×Δs, 每道光圈 Δs=λ/2",
        )

        _step(
            "5. 最大矢高与曲率半径反推",
            r"s_{\max} = s + \Delta s \qquad"
            r"R_{\max} = \frac{CA^2}{8\,s_{\max}} + \frac{s_{\max}}{2}",
            f"  S1:  s_max₁ = {r.sag_s1:.6f} + {r.sag_diff_s1:.6f} = {r.sag_max_s1:.6f} mm\n"
            f"       R_max₁ = {ca1}²/(8×{r.sag_max_s1:.6f}) + {r.sag_max_s1:.6f}/2"
            f" = {r.r_max_s1:.4f} mm\n"
            f"  S2:  s_max₂ = {r.sag_s2:.6f} + {r.sag_diff_s2:.6f} = {r.sag_max_s2:.6f} mm\n"
            f"       R_max₂ = {ca2}²/(8×{r.sag_max_s2:.6f}) + {r.sag_max_s2:.6f}/2"
            f" = {r.r_max_s2:.4f} mm"
        )

        _step(
            "6. 曲率半径公差 ΔR",
            r"\Delta R = |\,|R_{\max}| - |R|\,|\qquad"
            r"R_{\text{upper}} = R + \Delta R\qquad"
            r"R_{\text{lower}} = R - \Delta R",
            f"  R₁:  ΔR = |{r.r_max_s1} − {abs(p.r1)}| = {r.r1_dr_no_sample:.4f} mm\n"
            f"       上限 = {p.r1} + {r.r1_dr_no_sample:.4f} = {r.r1_upper:.4f} mm\n"
            f"       下限 = {p.r1} − {r.r1_dr_no_sample:.4f} = {r.r1_lower:.4f} mm\n"
            f"  R₂:  ΔR = {r.r2_dr_no_sample:.4f} mm\n"
            f"       上限 = {p.r2} + {r.r2_dr_no_sample:.4f} = {r.r2_upper:.4f} mm\n"
            f"       下限 = {p.r2} − {r.r2_dr_no_sample:.4f} = {r.r2_lower:.4f} mm"
        )

        _step(
            "7. 毛坯下料尺寸",
            r"D_{\text{blank}} = D + \text{pre\_edge}\qquad"
            r"T_{\text{blank}} = T_c + \text{mill}_{S1} + \text{mill}_{S2}"
            r" + \text{grind/polish}_{S1} + \text{grind/polish}_{S2}",
            f"  毛坯口径 = {p.diameter} + {p.pre_edge} = {r.blank_diameter:.1f} mm\n"
            f"  毛坯厚度 = {p.tc} + {p.mill_s1} + {p.mill_s2}"
            f" + {p.grinding_polishing_s1} + {p.grinding_polishing_s2}"
            f" = {r.blank_thickness:.2f} mm"
        )

        _step(
            "8. 面倾斜与偏心换算",
            r"X\;({}') = \frac{c}{0.291\,(n-1)\,\text{BFL}} \times 1000"
            r"\qquad c = X \times 0.291 \times (n-1) \times \frac{\text{BFL}}{1000}",
            f"  参考偏心差 c = 0.008 mm\n"
            f"  S1:  面倾斜@0.008mm = 0.008/(0.291×{p.n-1}×{r.back_focal_s1:.2f})×1000"
            f" = {r.tilt_s1_per_mm:.2f}'\n"
            f"  S2:  面倾斜@0.008mm = 0.008/(0.291×{p.n-1}×{r.back_focal_s2:.2f})×1000"
            f" = {r.tilt_s2_per_mm:.2f}'"
        )

        _step(
            "9. 球心距（面倾斜 → 球心偏移）",
            r"a = \frac{X \times R}{3438}",
            f"  S1:  a = 1′ × {p.r1} / 3438 = {r.sphere_center_s1:.4f} mm\n"
            f"  S2:  a = 1′ × {p.r2} / 3438 = {r.sphere_center_s2:.4f} mm",
            note="弧分→弧度换算: 3438 ≈ 180×60/π",
        )

        _step(
            "10. 边厚差",
            r"\Delta t_{\text{edge}} = \frac{D \times c}{R}",
            f"  边厚差@0.004mm偏心 = {p.diameter}×0.004/{abs(p.r1):.4f}"
            f" = {r.edge_thick_diff_s1:.4f} mm"
        )

        canvas.yview_moveto(0)


if __name__ == "__main__":
    root = tk.Tk()
    state = AppState()
    state.load_user_params()
    ProcessPlanApp(root, app_state=state)
    root.mainloop()
