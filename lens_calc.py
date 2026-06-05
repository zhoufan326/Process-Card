r"""球面透镜参数计算核心。

根据透镜物理参数和加工参数，自动计算焦距、后焦距、
偏心差、面倾斜、曲率半径公差范围、矢高、下料尺寸等工艺指标。

字段定义由 field_schema.json 统一管理。
"""

import json
import math
import os
from dataclasses import dataclass, make_dataclass, field


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
    """所有计算结果 — 对应工艺卡(GUI右侧/Excel)中的计算输出项。"""

    # ── 基本光学参数 ── (GUI右侧"基本光学参数"区域 / 工艺卡E4"焦距")
    focal_length: float = 0.0          # 焦距 f (mm), 透镜制造者公式计算结果
    back_focal_s1: float = 0.0         # 后焦距 BFL_S1 (mm), S1面方向的后截距
    back_focal_s2: float = 0.0         # 后焦距 BFL_S2 (mm), S2面方向的后截距

    # ── 下料 / 毛坯尺寸 ── (GUI右侧"下料/毛坯尺寸"区域 / 工艺卡D4"ΦD×Tc")
    blank_diameter: float = 0.0        # 毛坯外径 (mm), = D + pre_edge
    blank_thickness: float = 0.0       # 下料中心厚度 (mm), 各工序去除量累加
    s1_ca_strict: float = 0.0          # S1 加严CA (mm), 按毛坯比例放大检测口径
    s2_ca_strict: float = 0.0          # S2 加严CA (mm)

    # ── 工序厚度 ── (GUI右侧"工序中厚"区域)
    tc_after_mill_s1: float = 0.0      # 铣磨S1后中心厚 (mm)
    tc_after_mill_s2: float = 0.0      # 铣磨S2后中心厚 (mm)
    tc_after_grinding_s1: float = 0.0  # 精抛S1后中心厚 (mm), 即产品最终Tc
    tc_after_grinding_s2: float = 0.0  # 精抛S2后中心厚 (mm), 校验值与原始Tc一致

    # ── 精磨量 / 抛光量拆分 ── (GUI右侧"去除量拆分"区域)
    # polishing 固定为 0.02mm, grinding = grinding_polishing - polishing
    grinding_s1: float = 0.0           # S1 精磨去除量 (mm)
    grinding_s2: float = 0.0           # S2 精磨去除量 (mm)
    polishing_s1: float = 0.0          # S1 抛光去除量 (mm), 固定 0.02
    polishing_s2: float = 0.0          # S2 抛光去除量 (mm), 固定 0.02

    # ── 矢高 ── (GUI右侧"矢高"区域 / 工艺卡间接体现)
    sag_s1: float = 0.0                # S1 标准矢高 (mm), 由R₁和CA₁通过球面公式算出
    sag_s2: float = 0.0                # S2 标准矢高 (mm)
    sag_diff_s1: float = 0.0           # S1 最大矢高差 (mm), = N₁ × λ/2 (牛顿环光圈换算)
    sag_diff_s2: float = 0.0           # S2 最大矢高差 (mm)
    sag_max_s1: float = 0.0            # S1 最大矢高 (mm), = sag₁ + sag_diff₁
    sag_max_s2: float = 0.0            # S2 最大矢高 (mm)
    r_max_s1: float = 0.0              # S1 R最大值 (mm), 由sag_max₁反推的曲率半径
    r_max_s2: float = 0.0              # S2 R最大值 (mm)

    # ── 曲率半径公差 ── (GUI右侧"曲率半径公差"区域 / 工艺卡F4/F5"R值")
    r1_sample_precision: float = 0.0   # R₁ A级样板精度 (µm), 按|R|分五档
    r2_sample_precision: float = 0.0   # R₂ A级样板精度 (µm)
    r1_dr_with_sample: float = 0.0     # R₁ ΔR含样板 (mm), = |R_max-R| + 样板精度
    r1_dr_no_sample: float = 0.0       # R₁ ΔR不含样板 (mm), 零件本身制造公差
    r1_upper: float = 0.0              # R₁ 上限 (mm), = R₁ + ΔR(不含样板)
    r1_lower: float = 0.0              # R₁ 下限 (mm), = R₁ - ΔR(不含样板)
    r2_dr_with_sample: float = 0.0     # R₂ ΔR含样板 (mm)
    r2_dr_no_sample: float = 0.0       # R₂ ΔR不含样板 (mm)
    r2_upper: float = 0.0              # R₂ 上限 (mm)
    r2_lower: float = 0.0              # R₂ 下限 (mm)
    r1_actual_upper: str = ""          # R₁ 实际显示上限文本 (小R值→µm, 大R值→mm数值)
    r1_actual_lower: str = ""          # R₁ 实际显示下限文本
    r2_actual_upper: str = ""          # R₂ 实际显示上限文本
    r2_actual_lower: str = ""          # R₂ 实际显示下限文本

    # ── 偏心 / 面倾斜 ── (GUI右侧"偏心/面倾斜"区域 / 工艺卡I4/I5"透射偏心")
    tilt_s1_per_mm: float = 0.0        # S1 面倾斜X ('/mm), 参考偏心c=0.008mm换算
    tilt_s2_per_mm: float = 0.0        # S2 面倾斜X ('/mm)
    decent_s1_per_tilt: float = 0.0    # S1 偏心差c (mm/@1'), 1′面倾斜对应的偏心量
    decent_s2_per_tilt: float = 0.0    # S2 偏心差c (mm/@1')
    sphere_center_s1: float = 0.0      # S1 球心距a (mm/@1'), 1′面倾斜对应的球心偏移
    sphere_center_s2: float = 0.0      # S2 球心距a (mm/@1')
    reflect_center_s1: float = 0.0     # S1 反射球心距 (mm), 用于镜面检测转换
    reflect_center_s2: float = 0.0     # S2 反射球心距 (mm)
    edge_thick_diff_s1: float = 0.0    # 边厚差Δt (mm/@0.004mm偏心), 工艺卡厚度均匀性参考

    # ── 面倾斜(球心距反算) ── (GUI右侧"面倾斜(球心距反算)"区域)
    tilt_from_center_s1: float = 0.0   # S1 面倾斜X ('), 由反射球心距反算得出
    tilt_from_center_s2: float = 0.0   # S2 面倾斜X (')


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
    # 1/f = (n-1)*(1/R1 - 1/R2) + (n-1)^2 * Tc / (n * R1 * （-R2）)
    #这里给R2取负号，采用Zemax中的判断方式。（原本是凸正凹负
    term1 = (p.n - 1) * (1.0 / p.r1 - 1.0 / (-p.r2))
    term2 = (p.n - 1) ** 2 * p.tc / (p.n * p.r1 * (-p.r2))
    focal = 1.0 / (term1 + term2)
    r.focal_length = round(focal, 4)

    # ── 后焦距 ──
    # BFL = f * (1 - Tc*(n-1)/(n*R))
    bfl_s1 = focal * (1 - p.tc * (p.n - 1) / (p.n * p.r1))
    bfl_s2 = focal * (1 - p.tc * (p.n - 1) / (p.n * (-p.r2)))
    r.back_focal_s1 = round(bfl_s1, 2)
    r.back_focal_s2 = round(bfl_s2, 2)

    # ── 下料尺寸 ──
    r.blank_diameter = round(p.diameter + p.pre_edge, 1)
    # 下料中心厚度 = Tc + 铣磨S1 + 铣磨S2 + 精磨抛光S1 + 精磨抛光S2
    raw_thick = p.tc + p.mill_s1 + p.mill_s2 + p.grinding_polishing_s1 + p.grinding_polishing_s2
    r.blank_thickness = round(raw_thick, 2)

    # ── 加严 CA（检测口径按毛坯比例放大）──
    # 加严 CA = 原 CA × 毛坯外径 / 成品外径
    # 例如：CA=44, blank_D=50, D=48 → 加严 CA=44.9
    r.s1_ca_strict = round(p.s1_ca * (r.blank_diameter - p.pre_edge/2) / p.diameter, 1)
    r.s2_ca_strict = round(p.s2_ca * (r.blank_diameter - p.pre_edge/2) / p.diameter, 1)

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
    sag_per_fringe = p.wavelength * 1e-6 / 2
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
