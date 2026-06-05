r"""工艺卡片 Excel 生成器。

根据 manufacturing_process.json 的工序数据和 process_planning 的计算结果，
生成参照 M0454-G10 格式的完整工艺卡片 Excel。

字体: 等线  填充色: 黄#FFFF00 橙#FFC000
工序表头三色: A-E#D9E1F4  F-J#E3F2D9  K-M#DCE6F2
"""

import json, os, datetime
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill, Alignment, Border, Side, Font
from openpyxl.utils import get_column_letter

from set import Tasks, load_preset
from lens_calc import LensParams, CalcResult, calculate

# ═══ Schema ═══
def _load_schema() -> dict:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_schema.json")
    with open(p, "r", encoding="utf-8") as f: return json.load(f)
_SCHEMA = _load_schema()

# ═══ 样式 ═══
_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_ALIGN_C = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_L = Alignment(horizontal="left", vertical="center", wrap_text=True)
_F = {
    "title":  Font(name="等线", size=16, bold=True),  # 卡片标题
    "sec":    Font(name="等线", size=14, bold=True),  # 分区标题
    "lbl":    Font(name="等线", size=12, bold=True),  # 材料/图号/镀膜
    "bold11": Font(name="等线", size=11, bold=True),  # 列头/数值/表体
    "bold10": Font(name="等线", size=10, bold=True),  # HK/FA
    "11":     Font(name="等线", size=11)              # 表体非粗
}
_FILL_NONE = PatternFill(fill_type=None)
_FL = {
    "h1": PatternFill(start_color="D9E1F4", end_color="D9E1F4", fill_type="solid"),
    "h2": PatternFill(start_color="E3F2D9", end_color="E3F2D9", fill_type="solid"),
    "h3": PatternFill(start_color="DCE6F2", end_color="DCE6F2", fill_type="solid"),
    "yellow": PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid"),
    "orange": PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid"),
}
_BAY_C = {"成形":"00B0F0","球面":"FFC000","平面":"FFC000","清洗":"FF0000","镀膜":"00B050"}


def _irr_rms_str(irr: float, rms: float) -> str:
    """面形列：IRR 和 RMS 条件组合。值为 0 时跳过。"""
    parts = []
    if irr: parts.append(f"IRR:{irr}\u03bb")
    if rms: parts.append(f"RMS:{rms:.0f}nm")
    return ", ".join(parts)


def _cell(ws, ref, val, font=None, fill=None, align=_ALIGN_C, border=_BORDER_ALL):
    """写入单元格。ref 为 Excel 引用如 'B3' 或 'AB12'。"""
    col = openpyxl.utils.cell.column_index_from_string(ref.rstrip("0123456789"))
    row = int("".join(c for c in ref if c.isdigit()))
    c = ws.cell(row=row, column=col, value=val)
    c.font = font or _F["bold11"]
    c.fill = fill or _FILL_NONE
    c.alignment = align
    c.border = border
    return c


def _bay_fill(bay):
    for p, c in _BAY_C.items():
        if bay.startswith(p): return PatternFill(start_color=c,end_color=c,fill_type="solid")
    return None


def _make_ctx(p, r):
    ctx = {}
    for item in _SCHEMA["export_ctx"]:
        if "ctx" not in item: continue
        src = p if item["source"]=="params" else r
        val = getattr(src, item["attr"])
        if item.get("hide_zero"):
            try:
                if float(val) == 0.0:
                    ctx[item["ctx"]] = ""; continue
            except (ValueError, TypeError):
                if not val: ctx[item["ctx"]] = ""; continue
        text = str(val) if item["fmt"]=="s" else format(val, item["fmt"])
        if item.get("prefix"): text = item["prefix"] + text
        if item.get("suffix"): text += item["suffix"]
        ctx[item["ctx"]] = text
    return ctx


# ═══ 主入口 ═══
def generate_process_card(filepath: str, *, lens_params=None, calc_result=None):
    p = lens_params or LensParams()
    r = calc_result or calculate(p)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "工艺卡"
    _cl = get_column_letter
    
    
    # ── 列宽 ──
    for l, w in {"A":12,"B":20,"C":12,"D":16,"E":50,"F":14,"G":10,
                 "H":15,"I":20,"J":20,"K":15,"L":15,"M":15,"N":15,"O":15,"P":15}.items():
        ws.column_dimensions[get_column_letter(openpyxl.utils.cell.column_index_from_string(l))].width = w

   
    
    
    # ── 行1-2: 标题 A1:H2 + I-O 标签/值 ──
    _cell(ws, "A1", "球面透镜加工工艺卡", font=_F["title"])
    ws.merge_cells("A1:H2")
    ws.row_dimensions[1].height = ws.row_dimensions[2].height = 28

    # 行1 标签 — 材料  I1
    _cell(ws, "I1", "材料", font=_F["lbl"])
    # 产品类型  J1-K1 合并
    _cell(ws, "J1", "产品类型", font=_F["lbl"]); ws.merge_cells("J1:K1")
    # 图号  L1-M1 合并
    _cell(ws, "L1", "图号", font=_F["lbl"]); ws.merge_cells("L1:M1")
    # 工艺卡号  N1-O1 合并
    _cell(ws, "N1", "工艺卡号", font=_F["lbl"]); ws.merge_cells("N1:O1")

    # 行2 值
    _cell(ws, "I2", p.material, font=_F["lbl"])
    _cell(ws, "J2", p.lens_type, font=_F["lbl"]); ws.merge_cells("J2:K2")
    _cell(ws, "L2", p.drawing_no, font=_F["lbl"]); ws.merge_cells("L2:M2")
    _cell(ws, "N2", p.card_no, font=_F["lbl"]); ws.merge_cells("N2:O2")

    # ── 行3-7: 技术指标 + 镀膜 ──
    _cell(ws, "A3", "技术指标", font=_F["bold11"]); ws.merge_cells("A3:A5")
    # 行3 列头
    _cell(ws, "B3", "面次",     font=_F["bold11"])
    _cell(ws, "C3", "加工方式", font=_F["bold11"])
    _cell(ws, "D3", "尺寸",     font=_F["bold11"])
    _cell(ws, "E3", "焦距",     font=_F["bold11"])
    _cell(ws, "F3", "R值",      font=_F["bold11"])
    _cell(ws, "G3", "S/D",      font=_F["bold11"])
    _cell(ws, "H3", "CA",       font=_F["bold11"])
    _cell(ws, "I3", "透射偏心", font=_F["bold11"])
    _cell(ws, "J3", "面形",     font=_F["bold11"])
    _cell(ws, "K3", "崩边",     font=_F["bold11"])
    _cell(ws, "L3", "倒角", font=_F["bold11"])
    _cell(ws, "N3", "粗糙度", font=_F["bold11"])
    _cell(ws, "O3", "单位", font=_F["bold11"])
    ws.row_dimensions[3].height = 32

    cd = lambda v: f"\uff1e\u03a6{v}"
    # 行4 S1
    _cell(ws, "B4", "S1",                                     font=_F["bold11"])
    _cell(ws, "C4", "抛光",                                   font=_F["bold11"])
    _cell(ws, "D4", f"\u03a6{p.diameter}\u00d7{p.tc}(Tc)",   font=_F["bold11"])
    _cell(ws, "E4", f"{r.focal_length:.0f}@589nm",            font=_F["bold11"])
    _cell(ws, "F4", f"{p.r1:.3f}" if p.r1 else "平面",       font=_F["bold11"])
    _cell(ws, "G4", p.s1_sd,                                  font=_F["bold11"])
    _cell(ws, "H4", cd(p.s1_ca),                              font=_F["bold11"])
    _cell(ws, "I4", f"\uff1c{r.tilt_s1_per_mm:.1f}\u2032",   font=_F["bold11"])
    _cell(ws, "J4", _irr_rms_str(p.s1_irr, p.s1_rms),        font=_F["bold11"])
    _cell(ws, "K4", f"\uff1c{p.edge_chip}",                   font=_F["bold11"])
    _cell(ws, "L4", p.chamfer,                                font=_F["bold11"])
    _cell(ws, "N4", f"\uff1c{p.s1_rms}nm",                  font=_F["bold11"])
    _cell(ws, "O4", "mm",                          font=_F["bold11"]); ws.merge_cells("O4:O5")
    #-先写 O4 为 "mm" ，然后立即 merge_cells("O4:O5") → O5 变成了 MergedCell
    #-再次写 O5 为 "nm / ' / mm" → MergedCell 不可写入，报错
    
    ws.row_dimensions[4].height = 28

    # 行5 S2
    _cell(ws, "B5", "S2",                                     font=_F["bold11"])
    _cell(ws, "C5", "抛光",                                   font=_F["bold11"])
    _cell(ws, "F5", f"{p.r2:.3f}" if p.r2 else "平面",       font=_F["bold11"])
    _cell(ws, "G5", p.s2_sd,                                  font=_F["bold11"])
    _cell(ws, "H5", cd(p.s2_ca),                              font=_F["bold11"])
    _cell(ws, "I5", f"\uff1c{r.tilt_s2_per_mm:.1f}\u2032",   font=_F["bold11"])
    _cell(ws, "J5", _irr_rms_str(p.s2_irr, p.s2_rms),        font=_F["bold11"])
    _cell(ws, "K5", f"\uff1c{p.edge_chip}",                   font=_F["bold11"])
    _cell(ws, "L5", p.chamfer,                                font=_F["bold11"])
    _cell(ws, "N5", f"\uff1c{p.s2_rms}nm",                  font=_F["bold11"])

    ws.row_dimensions[5].height = 28

    # 行6-7: 镀膜指标
    _cell(ws, "A6", "镀膜指标", font=_F["bold11"]); ws.merge_cells("A6:A7")
    _cell(ws, "B6", p.coating_spec, font=_F["lbl"]); ws.merge_cells("B6:H7")
    _cell(ws, "I6", "DW耐水作用稳定性", font=_F["bold11"])
    _cell(ws, "J6", "DA耐酸作用稳定性", font=_F["bold11"])
    _cell(ws, "K6", "CR耐候性",         font=_F["bold11"])
    _cell(ws, "L6", "RC耐潮稳定性",     font=_F["bold11"])
    _cell(ws, "M6", "RA耐酸稳定性",     font=_F["bold11"])
    ws.row_dimensions[6].height = 28

    _cell(ws, "N6", "HK努氏硬度", font=_F["bold11"]);   _cell(ws, "N7", "522kg/mm\u00b2", font=_F["bold10"])
    _cell(ws, "O6", "FA磨耗度", font=_F["bold11"]);     _cell(ws, "O7", "50", font=_F["bold10"])
    ws.row_dimensions[7].height = 28
    ws.merge_cells("D4:D5"); ws.merge_cells("E4:E5"); ws.merge_cells("L4:M4"); ws.merge_cells("L5:M5")

    # ── 行8-11: 黄底分区 + 副标题 + 产品类型/图号/卡号 ──
    _cell(ws, "A8", "", font=_F["sec"], fill=_FL["yellow"])
    ws.merge_cells("A8:O8"); ws.row_dimensions[8].height = 24
    _cell(ws, "A9", "球面透镜加工工艺卡", font=_F["sec"], fill=_FL["orange"])
    ws.merge_cells("A9:C9"); ws.row_dimensions[9].height = 22
    _cell(ws, "J9", "版次", font=_F["bold11"])
    _cell(ws, "K9", "A", font=_F["bold11"])
    _cell(ws, "L9", "页次", font=_F["bold11"])
    _cell(ws, "M9", "1/1", font=_F["bold11"])
    _cell(ws, "N9", "工序名称", font=_F["bold11"])
    _cell(ws, "O9", "总流程", font=_F["bold11"])
    _cell(ws, "A10", "产品类型", font=_F["bold11"], fill=_FL["orange"])
    _cell(ws, "B10", "图号", font=_F["bold11"], fill=_FL["orange"])
    _cell(ws, "C10", "工艺卡号", font=_F["bold11"], fill=_FL["orange"])
    _cell(ws, "J10", "制定", font=_F["bold11"])
    _cell(ws, "J11", "审核", font=_F["bold11"])
    _cell(ws, "K10", p.author, font=_F["11"]); ws.merge_cells("K10:L10")
    _cell(ws, "K11", p.reviewer, font=_F["11"]); ws.merge_cells("K11:L11")
    _cell(ws, "N10", p.approver, font=_F["11"]); ws.merge_cells("N10:O11")
    _cell(ws, "A11", p.lens_type, font=_F["bold11"], fill=_FL["orange"])
    _cell(ws, "B11", p.drawing_no, font=_F["bold11"], fill=_FL["orange"])
    _cell(ws, "C11", p.card_no, font=_F["bold11"], fill=_FL["orange"])
    
    ws.row_dimensions[10].height = ws.row_dimensions[11].height = 22

    # ── 行12: 工序表头 (A-E 蓝灰 / F-J 浅绿 / K-M 淡蓝灰) ──
    _cell(ws, "A12", "序号",     font=_F["bold11"], fill=_FL["h1"])
    _cell(ws, "B12", "车间",     font=_F["bold11"], fill=_FL["h1"])
    _cell(ws, "C12", "工序",     font=_F["bold11"], fill=_FL["h1"])
    _cell(ws, "D12", "对象",     font=_F["bold11"], fill=_FL["h1"])
    _cell(ws, "E12", "技术参数", font=_F["bold11"], fill=_FL["h1"])
    ws.merge_cells("E12:G12")
    _cell(ws, "H12", "检验项目", font=_F["bold11"], fill=_FL["h2"])
    _cell(ws, "I12", "检验类型", font=_F["bold11"], fill=_FL["h2"])
    _cell(ws, "J12", "检验\n标准", font=_F["bold11"], fill=_FL["h2"])
    _cell(ws, "K12", "设备",    font=_F["bold11"], fill=_FL["h3"])
    _cell(ws, "L12", "工装",    font=_F["bold11"], fill=_FL["h3"])
    _cell(ws, "M12", "图片",    font=_F["bold11"], fill=_FL["h3"])
    ws.merge_cells("M12:O12"); ws.row_dimensions[12].height = 30

    # ── 行13+: 工序数据 ──
    ctx = _make_ctx(p, r)
    seq, row, bf = 0, 13, {}
    for g in Tasks:
        bay = g.bay.strip(); proc = g.process.strip(); obj = g.obj.strip() if g.obj else ""
        fill = bf.setdefault(bay, _bay_fill(bay))
        seq += 1; gs = row
        for i, rt in enumerate(g.requires):
            req = rt.strip()
            for k, v in ctx.items(): req = req.replace(k, v)
            _cell(ws, f"A{row}", seq, font=_F["bold11"], fill=fill)
            _cell(ws, f"B{row}", bay if i == 0 else "", font=_F["bold11"], fill=fill)
            _cell(ws, f"C{row}", proc if i == 0 else "", font=_F["bold11"], fill=fill)
            _cell(ws, f"D{row}", obj if i == 0 else "", font=_F["bold11"], fill=fill)
            _cell(ws, f"E{row}", req, font=_F["11"], align=_ALIGN_C)
            for c in range(6, 14): _cell(ws, f"{_cl(c)}{row}", "", font=_F["bold11"])
            ws.row_dimensions[row].height = max(20, 14 * max(1, len(req) // 40))
            row += 1
        ge = row - 1
        if ge > gs:
            for c in (1, 2, 3, 4): ws.merge_cells(start_row=gs, start_column=c, end_row=ge, end_column=c)
    last_row = row - 1
    ws.merge_cells(start_row=13, start_column=13, end_row=last_row, end_column=15)
    for mr in range(13, last_row + 1): ws.merge_cells(start_row=mr, start_column=5, end_row=mr, end_column=7)
          #这里的5和7是列号，循环中代表E和G
    # ── 变更记录页脚 ──
    ft = last_row + 3
    _cell(ws, f"A{ft}", "变更记录", font=_F["sec"])
    ws.merge_cells(start_row=ft, start_column=1, end_row=ft, end_column=15)
    ws.row_dimensions[ft].height = 24

    # ft+1: 标签行
    _cell(ws, f"A{ft+1}", "版本",     font=_F["bold11"])
    _cell(ws, f"B{ft+1}", "变更内容", font=_F["bold11"])
    _cell(ws, f"J{ft+1}", "制/修订人",font=_F["bold11"])
    _cell(ws, f"K{ft+1}", "审核",     font=_F["bold11"])
    _cell(ws, f"L{ft+1}", "批准",     font=_F["bold11"])
    _cell(ws, f"M{ft+1}", "制/修订时间",font=_F["bold11"])
    ws.merge_cells(start_row=ft+1, start_column=2, end_row=ft+1, end_column=9)
    ws.merge_cells(start_row=ft+1, start_column=13, end_row=ft+1, end_column=15)
    ws.row_dimensions[ft+1].height = 22

    # ft+2: 数据行
    _cell(ws, f"A{ft+2}", "A",          font=_F["bold11"])
    _cell(ws, f"B{ft+2}", "新增",       font=_F["bold11"])
    _cell(ws, f"J{ft+2}", p.author,    font=_F["11"])
    _cell(ws, f"K{ft+2}", p.reviewer,  font=_F["11"])
    _cell(ws, f"L{ft+2}", p.approver,  font=_F["11"])
    today = datetime.date.today()
    _cell(ws, f"M{ft+2}", f"{today.year}.{today.month}.{today.day}",  font=_F["11"])
    ws.merge_cells(start_row=ft+2, start_column=2, end_row=ft+2, end_column=9)
    ws.merge_cells(start_row=ft+2, start_column=13, end_row=ft+2, end_column=15)
    ws.row_dimensions[ft+2].height = 22

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr = None
    wb.save(filepath)
    return ws.max_row


def export_process_card(filepath: str, lens_params=None, preset_path="manufacturing_process.json"):
    if os.path.exists(preset_path): load_preset(preset_path)
    p = lens_params or LensParams()
    r = calculate(p)
    generate_process_card(filepath, lens_params=p, calc_result=r)
    return r
