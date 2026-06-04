r"""工艺方案设计 — 球面透镜参数计算。

根据透镜物理参数和加工参数，自动计算焦距、后焦距、
偏心差、面倾斜、曲率半径公差范围、矢高、下料尺寸等工艺指标。

字段定义由 field_schema.json 统一管理。
"""

import json
import math
import os
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, make_dataclass, field

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

# ═══ 加载字段 Schema ═══

def _load_schema() -> dict:
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

SCHEMA = _load_schema()

# ═══ 光学/工艺经验常数 ═══
# 以下常数来源于《工艺方案设计-王千奥.xlsx》中的工程经验值
_SAMPLE_PRECISION_THRESHOLD = 35.0   # R值分界点 (mm), <此值用μm, ≥用%
_TILT_CONST = 0.291                  # 偏心→面倾斜换算系数 (源于工艺经验)
_SPHERE_CENTER_CONST = 3438          # 角分→弧度换算 (弧分到弧度的简化: 3438 ≈ 180*60/π)
_FRINGE_CONST = 2.0                  # 反射式牛顿环：OPD=2×Δs → 每道光圈 Δs=λ/2


# ═══ 数据结构 ═══

_TYPE_PY = {"str": str, "float": float, "int": int}


def _flatten_fields():
    """将 gui_sections 展平为 (attr, type, default) 序列。"""
    for section in SCHEMA["gui_sections"]:
        for f in section["fields"]:
            if "attr" in f:
                yield f["attr"], _TYPE_PY[f["type"]], f.get("default")


def _make_lens_params():
    """由 field_schema.json 动态构建 LensParams dataclass。
    
    新增输入字段只需在 field_schema.json 中配置, 无需修改 Python 代码。
    """
    return make_dataclass(
        "LensParams",
        [(name, typ, field(default=default)) for name, typ, default in _flatten_fields()],
    )

LensParams = _make_lens_params()


@dataclass
class CalcResult:
    """所有计算结果。"""
    focal_length: float = 0.0
    back_focal_s1: float = 0.0
    back_focal_s2: float = 0.0

    blank_diameter: float = 0.0
    blank_thickness: float = 0.0
    s1_ca_strict: float = 0.0
    s2_ca_strict: float = 0.0

    tc_after_mill_s1: float = 0.0
    tc_after_mill_s2: float = 0.0
    tc_after_grinding_s1: float = 0.0
    tc_after_grinding_s2: float = 0.0

    # 精磨 / 抛光（由总量 grinding_polishing 拆分得出）
    grinding_s1: float = 0.0
    grinding_s2: float = 0.0
    polishing_s1: float = 0.0
    polishing_s2: float = 0.0

    sag_s1: float = 0.0
    sag_s2: float = 0.0
    sag_diff_s1: float = 0.0
    sag_diff_s2: float = 0.0
    sag_max_s1: float = 0.0
    sag_max_s2: float = 0.0
    r_max_s1: float = 0.0
    r_max_s2: float = 0.0

    r1_sample_precision: float = 0.0
    r2_sample_precision: float = 0.0
    r1_dr_with_sample: float = 0.0
    r1_dr_no_sample: float = 0.0
    r1_upper: float = 0.0
    r1_lower: float = 0.0
    r2_dr_with_sample: float = 0.0
    r2_dr_no_sample: float = 0.0
    r2_upper: float = 0.0
    r2_lower: float = 0.0
    r1_actual_upper: str = ""
    r1_actual_lower: str = ""
    r2_actual_upper: str = ""
    r2_actual_lower: str = ""

    tilt_s1_per_mm: float = 0.0
    tilt_s2_per_mm: float = 0.0
    decent_s1_per_tilt: float = 0.0
    decent_s2_per_tilt: float = 0.0
    sphere_center_s1: float = 0.0
    sphere_center_s2: float = 0.0
    reflect_center_s1: float = 0.0
    reflect_center_s2: float = 0.0
    edge_thick_diff_s1: float = 0.0

    tilt_from_center_s1: float = 0.0
    tilt_from_center_s2: float = 0.0


# ═══ 辅助函数 ═══

def _safe_div(a: float, b: float) -> float:
    try: return a / b
    except (ZeroDivisionError, ValueError): return 0.0

def _sag(r_val: float, dia: float) -> float:
    ar = abs(r_val)
    half = dia / 2.0
    if half >= ar:
        return ar
    return ar - math.sqrt(ar ** 2 - half ** 2)

def _r_from_sag(s: float, dia: float) -> float:
    if s <= 0: return float('inf')
    return (dia ** 2) / (8 * s) + s / 2

def _sample_precision(rv: float) -> float:
    ar = abs(rv)
    if ar >= _SAMPLE_PRECISION_THRESHOLD:
        return 0.01 if ar > 1000 else 0.02
    if ar > 10: return 2.0
    return 1.0 if ar > 5 else 0.5

def _to_mm(precision: float, rv: float) -> float:
    if abs(rv) < _SAMPLE_PRECISION_THRESHOLD:
        return precision / 1000.0
    return precision / 100.0 * abs(rv)


# ═══ 核心计算 ═══

def calculate(p: LensParams) -> CalcResult:
    r = CalcResult()

    # ── 焦距 (透镜制造者公式) ──
    # 1/f = (n-1)*(1/R1 - 1/R2) + (n-1)^2 * Tc / (n * R1 * R2)
    term1 = (p.n - 1) * (1.0 / p.r1 - 1.0 / p.r2)
    term2 = (p.n - 1) ** 2 * p.tc / (p.n * p.r1 * p.r2)
    focal = 1.0 / (term1 + term2)
    r.focal_length = round(focal, 4)

    # ── 后焦距 ──
    # BFL = f * (1 - Tc*(n-1)/(n*R))
    bfl_s1 = focal * (1 - p.tc * (p.n - 1) / (p.n * p.r1))
    bfl_s2 = focal * (1 - p.tc * (p.n - 1) / (p.n * p.r2))
    r.back_focal_s1 = round(bfl_s1, 2)
    r.back_focal_s2 = round(bfl_s2, 2)

    # ── 下料尺寸 ──
    r.blank_diameter = round(p.diameter + p.pre_edge, 1)
    # 下料中心厚度 = Tc + 铣磨S1 + 铣磨S2 + 精磨抛光S1 + 精磨抛光S2
    raw_thick = p.tc + p.mill_s1 + p.mill_s2 + p.grinding_polishing_s1 + p.grinding_polishing_s2
    r.blank_thickness = round(raw_thick, 2)

    # ── 加严 CA（检测口径按毛坯比例放大）──
    # 加严 CA = 原 CA × 毛坯外径 / 成品外径
    # 例如：CA=44, blank_D=50, D=48 → 加严 CA=45.8
    r.s1_ca_strict = round(p.s1_ca * r.blank_diameter / p.diameter, 1)
    r.s2_ca_strict = round(p.s2_ca * r.blank_diameter / p.diameter, 1)

    # ── 精磨量 / 抛光量拆分 ──
    # polishing 固定为 0.02mm，grinding = grinding_polishing - polishing
    r.polishing_s1 = 0.02
    r.polishing_s2 = 0.02
    r.grinding_s1  = round(p.grinding_polishing_s1 - r.polishing_s1, 2)
    r.grinding_s2  = round(p.grinding_polishing_s2 - r.polishing_s2, 2)

    # ── 工序厚度 (逐层扣除) ──
    r.tc_after_mill_s1         = round(raw_thick - p.mill_s1, 2)                          # 铣磨S1后
    r.tc_after_mill_s2         = round(r.tc_after_mill_s1 - p.mill_s2, 2)                 # 铣磨S2后
    r.tc_after_grinding_s1     = round(r.tc_after_mill_s2 - p.grinding_polishing_s1, 2)   # 抛光S1后（S2待抛）
    r.tc_after_grinding_s2     = round(r.tc_after_grinding_s1 - p.grinding_polishing_s2, 2)  # 抛光S2后 = 原始Tc（校验）

    # ── 矢高 ──
    # 自动限制 CA ≤ 外径 (避免物理上不存在的区域计算崩溃)
    ca1 = min(p.s1_ca, p.diameter)
    ca2 = min(p.s2_ca, p.diameter)
    r.sag_s1 = round(_sag(p.r1, ca1), 6)
    r.sag_s2 = round(_sag(p.r2, ca2), 6)

    # 矢高差 = N × λ/2 (反射式牛顿环: OPD=2×Δs → 每道光圈 Δs=λ/2, 单位mm)
    sag_per_fringe = p.wavelength * 1e-6 / _FRINGE_CONST
    r.sag_diff_s1 = round(p.s1_n * sag_per_fringe, 6)
    r.sag_diff_s2 = round(p.s2_n * sag_per_fringe, 6)
    r.sag_max_s1 = round(r.sag_s1 + r.sag_diff_s1, 6)
    r.sag_max_s2 = round(r.sag_s2 + r.sag_diff_s2, 6)

    # R最大值 (由最大矢高反推)
    r.r_max_s1 = round(_r_from_sag(r.sag_max_s1, ca1), 4)
    r.r_max_s2 = round(_r_from_sag(r.sag_max_s2, ca2), 4)

    # ── 曲率半径公差 ──
    r.r1_sample_precision = _sample_precision(p.r1)
    r.r2_sample_precision = _sample_precision(p.r2)

    precision_r1 = _to_mm(r.r1_sample_precision, p.r1)
    precision_r2 = _to_mm(r.r2_sample_precision, p.r2)

    # ΔR (含样板公差) = |R_max - R| + 样板精度
    r.r1_dr_with_sample = round(abs(abs(r.r_max_s1) - abs(p.r1)) + precision_r1, 4)
    r.r2_dr_with_sample = round(abs(abs(r.r_max_s2) - abs(p.r2)) + precision_r2, 4)
    # ΔR (不含样板公差)
    r.r1_dr_no_sample = round(abs(abs(r.r_max_s1) - abs(p.r1)), 4)
    r.r2_dr_no_sample = round(abs(abs(r.r_max_s2) - abs(p.r2)), 4)

    # R值上/下限
    # 注意: 使用不含样板公差的 ΔR（样板精度 ε 是检测工具误差，非零件本身偏差）
    r.r1_upper = round(p.r1 + r.r1_dr_no_sample, 4)
    r.r1_lower = round(p.r1 - r.r1_dr_no_sample, 4)
    r.r2_upper = round(p.r2 + r.r2_dr_no_sample, 4)
    r.r2_lower = round(p.r2 - r.r2_dr_no_sample, 4)

    # 实际上下限文字
    for side in ('r1', 'r2'):
        rv = getattr(p, side)
        prec = getattr(r, f'{side}_sample_precision')
        if abs(rv) < _SAMPLE_PRECISION_THRESHOLD:
            text = f"{prec}\u00b5m"
            setattr(r, f'{side}_actual_upper', text)
            setattr(r, f'{side}_actual_lower', text)
        else:
            setattr(r, f'{side}_actual_upper', f"{getattr(r, f'{side}_upper'):.4f}")
            setattr(r, f'{side}_actual_lower', f"{getattr(r, f'{side}_lower'):.4f}")

    # ── 偏心 / 面倾斜 (使用工艺经验系数 _TILT_CONST ≈ 0.291) ──
    # 标准光学关系: 偏心 δ = (n-1) * BFL * θ
    # 此处 _TILT_CONST 为工艺经验校正值，非标准光学常数
    # 面倾斜X(') = |c/(0.291*(n-1)*BFL)| * 1000  (c=偏心差 mm)
    c_ref = 0.008  # 参考偏心差 0.008mm
    r.tilt_s1_per_mm = round(abs(_safe_div(c_ref, _TILT_CONST * (p.n - 1) * bfl_s1)) * 1000, 2)
    r.tilt_s2_per_mm = round(abs(_safe_div(c_ref, _TILT_CONST * (p.n - 1) * bfl_s2)) * 1000, 2)

    # 偏心差 c(mm) = X * 0.291 * (n-1) * BFL / 1000  (X=面倾斜 1')
    r.decent_s1_per_tilt = round(_TILT_CONST * (p.n - 1) * bfl_s1 / 1000, 5)
    r.decent_s2_per_tilt = round(_TILT_CONST * (p.n - 1) * bfl_s2 / 1000, 5)

    # 球心距 a(mm) = X * R / 3438
    r.sphere_center_s1 = round(p.r1 / _SPHERE_CENTER_CONST, 4)
    r.sphere_center_s2 = round(p.r2 / _SPHERE_CENTER_CONST, 4)

    # 反射球心距 (用于镜面检测转换)
    r.reflect_center_s1 = round(p.r1 * 0.004 / (p.r2 - p.r1), 6)
    r.reflect_center_s2 = round(p.r2 * 0.0025 / (p.r2 - p.r1), 6)

    # 反射球心距转化面倾斜
    r.tilt_from_center_s1 = round(_safe_div(_SPHERE_CENTER_CONST * 0.02, p.r1), 2)
    r.tilt_from_center_s2 = round(_safe_div(_SPHERE_CENTER_CONST * 0.02, p.r2), 2)

    # 边厚差 Δt = c * D / ((n-1) * BFL)
    r.edge_thick_diff_s1 = round(_safe_div(0.004 * p.diameter, (p.n - 1) * bfl_s1), 4)

    return r


# ═══ GUI ═══

class ProcessPlanApp:
    """球面透镜工艺计算 GUI。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._params = LensParams()
        self._build_ui()
        self._on_calculate()

    def _build_ui(self):
        r = self.root
        r.title("Process Card · 工艺方案计算")
        r.geometry("1100x660")
        r.minsize(900, 500)
        r.configure(bg=CLR_PAPER)

        h = tk.Frame(r, bg=CLR_HEADER, height=34)
        h.pack(fill="x")
        h.pack_propagate(False)
        tk.Label(h, text="\u25a0  球面透镜工艺方案设计计算",
                 font=(FONT, 11, "bold"), fg=CLR_TEXT, bg=CLR_HEADER).pack(
                     side="left", padx=14, pady=5)

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
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._build_input_fields(panel)

    def _build_result_panel(self, parent):
        right = tk.Frame(parent, bg=CLR_PANEL, highlightbackground=CLR_BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        self._result = tk.Text(right, font=("Consolas", 11), bg="#FAFAFA",
                               fg=CLR_TEXT, wrap="word", state="disabled", padx=10, pady=10)
        self._result.pack(fill="both", expand=True, padx=2, pady=2)

    def _build_footer(self, root):
        bf = tk.Frame(root, bg=CLR_HEADER, height=38)
        bf.pack(fill="x")
        bf.pack_propagate(False)
        tk.Button(bf, text="开始计算", command=self._on_calculate,
                  font=(FONT, 10, "bold"), bg=CLR_ACCENT, fg="white",
                  relief="flat", cursor="hand2", bd=0,
                  activebackground=CLR_ACCENT_HI, activeforeground="white",
                  width=12).pack(side="left", padx=14, pady=4)
        tk.Button(bf, text="应用", command=self._on_apply,
                  font=(FONT, 10), bg=CLR_ACCENT, fg="white",
                  relief="flat", cursor="hand2", bd=0,
                  activebackground=CLR_ACCENT_HI, activeforeground="white",
                  width=12).pack(side="left", padx=4, pady=4)
        self._status = tk.StringVar(value="就绪 — 请输入参数后点击「开始计算」")
        tk.Label(bf, textvariable=self._status, font=(FONT, 9),
                 fg=CLR_SUBTEXT, bg=CLR_HEADER, anchor="e").pack(side="right", padx=14, pady=4)

    # ═══════════════════════════════════════════════
    #  Schema-Driven 输入面板构建
    #  核心思想：字段定义在 field_schema.json 中，Python 代码只负责渲染
    #  优点：新增字段只需改 JSON，不改代码；UI 和逻辑解耦
    # ═══════════════════════════════════════════════

    def _build_input_fields(self, panel):
        """由 field_schema.json 驱动，自动生成全部输入控件。

        步骤拆解：
          1. 读取 LensParams 默认值（由 schema 动态构建的 dataclass）
          2. 遍历 SCHEMA["gui_sections"]，对每个 section 画标题 + 渲染字段
          3. 每个字段渲染为 [Label | Entry( + Unit)] 一行
        """
        self._entries = {}
        _DEFAULTS = LensParams()

        # ── 关于 _row = [0] ──
        # 为什么用列表而不是普通 int？
        # 因为 Python 闭包（nested function）只能「读」外层不可变变量，
        # 不能直接「修改」外层 int。列表是可变对象，_row[0] += 1 修改的是
        # 列表内容而非变量绑定，闭包可以捕获并修改。
        # 等效替代：用 nonlocal row；或直接用实例属性 self._row。
        _row = [0]

        # ── 1. 渲染 Section 标题 ──
        # 利用闭包捕获 panel、_row，减少重复传参
        def _section(title):
            tk.Label(panel, text=title, font=(FONT, 10, "bold"),
                     fg=CLR_ACCENT, bg=CLR_PANEL, anchor="w").grid(
                         row=_row[0], column=0, columnspan=2,
                         sticky="ew", padx=14, pady=(10, 2))
            _row[0] += 1

        # ── 2. 渲染单个字段行 ──
        # 布局：左侧标签(右对齐) | 右侧[输入框 + 可选单位标签]
        def _add_field(attr, label, unit=""):
            default = str(getattr(_DEFAULTS, attr))

            # 2a. 标签列（列0） — 右对齐，固定宽度 18 字符
            tk.Label(panel, text=label, font=(FONT, 9), fg=CLR_SUBTEXT,
                     bg=CLR_PANEL, anchor="e", width=18).grid(
                         row=_row[0], column=0, padx=(14, 4), pady=2, sticky="e")

            # 2b. 输入列（列1） — Entry + 可选单位
            frm = tk.Frame(panel, bg=CLR_PANEL)
            frm.grid(row=_row[0], column=1, sticky="ew", padx=(0, 14), pady=2)

            ent = tk.Entry(frm, font=(FONT, 9), width=18, bg="white",
                           fg=CLR_TEXT, relief="solid", bd=1)
            ent.pack(side="left")
            ent.insert(0, default)

            if unit:
                tk.Label(frm, text=unit, font=(FONT, 8), fg=CLR_SUBTEXT,
                         bg=CLR_PANEL).pack(side="left", padx=(4, 0))

            self._entries[attr] = ent
            _row[0] += 1

        # ── 3. Schema 驱动循环 ──
        # 遍历 SCHEMA["gui_sections"]，对每个 section：
        #   先画 section 标题，再渲染该 section 下的所有字段
        # 注意：schema 中可以包含 _comment 标记条目（不含 attr），需跳过
        for section in SCHEMA["gui_sections"]:
            _section(section["title"])
            for f in section["fields"]:
                if "attr" not in f:
                    continue
                _add_field(f["attr"], f["label"], f.get("unit", ""))

    # ═══════════════════════════════════════════════
    #  应用按钮 → Read-Modify-Write 模式
    #  将当前 GUI 输入值写回 field_schema.json 的 default 字段
    #  使得下次启动或主窗口同步时使用最新值
    # ═══════════════════════════════════════════════

    def _on_apply(self):
        """将当前所有输入值持久化到 field_schema.json 的 default 字段。

        流程（经典 Read-Modify-Write 模式）：
          Step 1 — Read:   读取 field_schema.json → schema 字典
          Step 2 — Modify: 遍历 gui_sections，用 Entry 内容覆盖 default
          Step 3 — Write:  将修改后的 schema 写回 JSON 文件

        类型处理：
          schema 中每个字段有 "type" 标记（float / int / str），
          写入时做类型转换，确保 JSON 输出正确的数据类型（而非全部存成字符串）。
        """
        schema_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "field_schema.json")

        # ── Step 1: Read ──
        # 注意：每次都重新从磁盘读取，而非使用模块级的 SCHEMA 常量
        # 原因：_on_calculate 可能已修改 SCHEMA，重新读取确保拿到最新磁盘内容
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("错误", f"无法读取 field_schema.json\n路径: {schema_path}\n原因: {e}")
            return

        # ── Step 2: Modify ──
        # 类型感知的 default 值更新：
        #   str   → 直接存（如材料名 "Corning 7980"）
        #   float → float(raw)，空字符串回退 0.0
        #   int   → int(raw)，空字符串回退 0
        for section in schema.get("gui_sections", []):
            for f in section.get("fields", []):
                if "attr" not in f or f["attr"] not in self._entries:
                    continue
                raw = self._entries[f["attr"]].get().strip()
                if f["type"] == "float":
                    f["default"] = float(raw) if raw else 0.0
                elif f["type"] == "int":
                    f["default"] = int(raw) if raw else 0
                else:
                    f["default"] = raw

        # ── Step 3: Write（带重试） ──
        # VS Code 打开 field_schema.json 时会持有写锁，导致写入失败。
        # 最多重试 3 次，每次间隔 0.5s，等待锁释放。
        import time
        success = False
        for attempt in range(3):
            try:
                with open(schema_path, "w", encoding="utf-8") as f:
                    json.dump(schema, f, ensure_ascii=False, indent=2)
                success = True
                break
            except OSError:
                if attempt < 2:
                    time.sleep(0.5)
                continue
        if success:
            messagebox.showinfo(
                "应用完成",
                "当前参数已更新到 field_schema.json。\n返回主窗口后参数将同步显示。")
            self._status.set("参数已应用")
        else:
            messagebox.showerror(
                "写入失败",
                "无法写入 field_schema.json，文件可能被占用。\n\n"
                "建议:\n"
                "1. 关闭 VS Code 中 field_schema.json 的标签页\n"
                "2. 关闭其他可能打开该文件的程序\n"
                "3. 稍后重试")

    # ── 校验 & 计算 ──

    def _validate(self, e: dict) -> str | None:
        """输入校验，返回错误信息或 None。
        校验规则:
          - R1/R2 不得为零
          - 折射率 n ≥ 1.0
          - Tc > 0
          - CA ≤ 外径 D (避免物理不存在的检测区域)
        """
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

    def _on_calculate(self):
        try:
            e = self._entries
            err = self._validate(e)
            if err:
                messagebox.showerror("输入错误", err)
                return

            # 由 field_schema.json 驱动构造 LensParams (JSON type→Python 类型映射)
            _TYPE_MAP = {"str": str, "float": float, "int": int}
            kwargs = {}
            for section in SCHEMA["gui_sections"]:
                for f in section["fields"]:
                    if "attr" not in f:     # 跳过 _comment 条目
                        continue
                    raw = e[f["attr"]].get().strip()
                    converter = _TYPE_MAP.get(f["type"], str)
                    kwargs[f["attr"]] = converter(raw)
            self._params = LensParams(**kwargs)

        except Exception as ex:
            messagebox.showerror("输入错误", f"参数读取失败:\n{ex}")
            return

        result = calculate(self._params)
        self._display_result(result)
        self._status.set(f"计算完成 — 焦距={result.focal_length}mm")

    # ── 结果展示 ──

    def _display_result(self, r: CalcResult):
        t = self._result
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.tag_configure("hdr", foreground=CLR_ACCENT, font=(FONT, 11, "bold"))

        def _h(text):
            t.insert("end", f"\n{'=' * 45}\n  {text}\n{'=' * 45}\n", "hdr")
        def _l(label, value, unit=""):
            t.insert("end", f"  {label:\u3000<18s} {value:>12} {unit}\n")

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


if __name__ == "__main__":
    root = tk.Tk()
    ProcessPlanApp(root)
    root.mainloop()
