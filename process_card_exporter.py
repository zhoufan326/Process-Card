r"""工艺卡片 Excel 生成器。

根据 manufacturing_process.json 的工序数据和 process_planning 的计算结果，
生成参照 M0454-G10 格式的完整工艺卡片 Excel。

字体: 等线  填充色: 黄#FFFF00 橙#FFC000
工序表头三色: A-E#D9E1F4  F-J#E3F2D9  K-M#DCE6F2
"""

import json, os
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill, Alignment, Border, Side, Font
from openpyxl.utils import get_column_letter

from set import Tasks, load_preset
from process_planning import LensParams, CalcResult, calculate

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
    "title": Font(name="等线", size=16, bold=True),
    "sec":   Font(name="等线", size=14, bold=True),
    "lbl":   Font(name="等线", size=12, bold=True),
    "h":     Font(name="等线", size=11, bold=True),
    "v":     Font(name="等线", size=11, bold=True),
    "b10":   Font(name="等线", size=10, bold=True),
    "b":     Font(name="等线", size=11, bold=True),
    "p":     Font(name="等线", size=11),
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
_PROC_H = [("A","序号",6),("B","车间",10),("C","工序",12),("D","对象",8),("E","技术参数",50),
           ("F","检验项目",14),("G","检验类型",10),("H","检验规格\n最小值",10),
           ("I","检验规格\n最大值",10),("J","检验\n标准",8),("K","设备",14),("L","工装",18),("M","图片",10)]

# ═══ 工具 ═══
def _cell(ws, row, col, val, font=None, fill=None, align=_ALIGN_C, border=_BORDER_ALL):
    c = ws.cell(row=row, column=col, value=val)
    c.font, c.fill, c.alignment, c.border = font or _F["b"], fill or _FILL_NONE, align, border
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

        # hide_zero: 当数值为 0 时输出空字符串
        if item.get("hide_zero"):
            try:
                if float(val) == 0.0:
                    ctx[item["ctx"]] = ""
                    continue
            except (ValueError, TypeError):
                if not val:
                    ctx[item["ctx"]] = ""
                    continue

        text = str(val) if item["fmt"]=="s" else format(val, item["fmt"])
        if item.get("prefix"): text = item["prefix"] + text
        if item.get("suffix"): text += item["suffix"]
        ctx[item["ctx"]] = text
    return ctx

# ═══ 主入口 ═══
def generate_process_card(filepath: str, *, lens_params=None, calc_result=None):
    p = lens_params or LensParams()
    r = calc_result or calculate(p)
    wb, ws = openpyxl.Workbook(), wb.active
    ws.title = "工艺卡"

    # 行1-2: 标题 A1:H2 + I-O 标签/值
    _cell(ws,1,1,"球面透镜加工工艺卡",font=_F["title"])
    ws.merge_cells("A1:H2")
    ws.row_dimensions[1].height=ws.row_dimensions[2].height=20
    for c,l in [(9,"材料"),(11,"产品类型"),(13,"图号"),(15,"工艺卡号")]:
        _cell(ws,1,c,l,font=_F["lbl"])
        ws.merge_cells(start_row=1,start_column=c,end_row=1,end_column=c+1)
    for c,v in [(9,p.material),(11,p.lens_type),(13,p.drawing_no),(15,p.card_no)]:
        _cell(ws,2,c,v,font=_F["lbl"])
        ws.merge_cells(start_row=2,start_column=c,end_row=2,end_column=c+1)

    # 行3-7: 技术指标 + 镀膜
    # A3:A5 合并填入"技术指标"
    _cell(ws,3,1,"技术指标",font=_F["h"]);
    ws.merge_cells("A3:A5")
    # 行3 列头 (B列起)
    for i,t in enumerate(["面次","加工方式","尺寸","焦距","R值","S/D","CA",
                          "透射偏心","面形","崩边","倒角","粗糙度","单位"],2):
        _cell(ws,3,i,t,font=_F["h"])
    ws.row_dimensions[3].height=32
    # 行4 S1
    cd = lambda v: f"\uff1e\u03a6{v}"
    for c,v in [(2,"S1"),(3,"抛光"),(4,f"\u03a6{p.diameter}\u00d7{p.tc}(Tc)"),
                (5,f"{r.focal_length:.0f}@589nm"),(6,f"{p.r1:.3f}" if p.r1 else "平面"),
                (7,p.s1_sd),(8,cd(p.s1_ca)),(9,f"\uff1c{r.tilt_s1_per_mm:.1f}\u2032"),
                (10,_irr_rms_str(p.s1_irr, p.s1_rms)),(11,f"\uff1c{p.edge_chip}"),
                (12,p.chamfer),(13,f"\uff1c{p.s1_rms}nm")]:
        _cell(ws,4,c,v,font=_F["v"])
    ws.row_dimensions[4].height=22
    # 行5 S2
    for c,v in [(2,"S2"),(3,"抛光"),(6,f"{p.r2:.3f}" if p.r2 else "平面"),
                (7,p.s2_sd),(8,cd(p.s2_ca)),(9,f"\uff1c{r.tilt_s2_per_mm:.1f}\u2032"),
                (10,_irr_rms_str(p.s2_irr, p.s2_rms)),(11,f"\uff1c{p.edge_chip}"),
                (12,p.chamfer),(13,f"\uff1c{p.s2_rms}nm")]:
        _cell(ws,5,c,v,font=_F["v"])
    ws.row_dimensions[5].height=22
    # 行6-7: 镀膜指标
    _cell(ws,6,1,"镀膜指标",font=_F["h"]);
    ws.merge_cells("A6:A7")
    _cell(ws,6,2,p.coating_spec,
          font=_F["lbl"])
    ws.merge_cells("B6:H7")
    for i,t in enumerate(["DW耐水作用稳定性","DA耐酸作用稳定性","CR耐候性","RC耐潮稳定性","RA耐酸稳定性"],10):
        _cell(ws,6,i,t,font=_F["h"])
    ws.row_dimensions[6].height=22
    # 行7 材料特性
    _cell(ws,7,13,"HK努氏硬度",font=_F["h"]); _cell(ws,7,14,"522kg/mm\u00b2",font=_F["b10"])
    _cell(ws,7,15,"FA磨耗度",font=_F["h"]);     _cell(ws,7,16,"50",font=_F["b10"])
    ws.row_dimensions[7].height=22
    # 合并
    ws.merge_cells("D4:D5"); ws.merge_cells("E4:E5")

    # 行8-11: 黄底分区 + 副标题 + 产品类型/图号/卡号
    _cell(ws,8,1,"球面透镜加工工艺卡",font=_F["sec"],fill=_FL["yellow"])
    ws.merge_cells("A8:O8")
    ws.row_dimensions[8].height=24
    _cell(ws,9,1,"球面透镜加工工艺卡",font=_F["sec"],fill=_FL["orange"]); ws.merge_cells("A9:C9"); ws.row_dimensions[9].height=22
    for c,t in [(1,"产品类型"),(2,"图号"),(3,"工艺卡号")]: _cell(ws,10,c,t,font=_F["h"],fill=_FL["orange"])
    for c,v in [(1,p.lens_type),(2,p.drawing_no),(3,p.card_no)]: _cell(ws,11,c,v,font=_F["v"],fill=_FL["orange"])
    ws.row_dimensions[10].height=ws.row_dimensions[11].height=22

    # 行12: 工序表头
    for cl,t,_ in _PROC_H:
        col = openpyxl.utils.cell.column_index_from_string(cl)
        fl = _FL["h1"] if col<=5 else (_FL["h2"] if col<=10 else _FL["h3"])
        _cell(ws,12,col,t,font=_F["b"],fill=fl)
    ws.row_dimensions[12].height=30

    # 行13+: 工序数据
    ctx = _make_ctx(p, r)
    seq, row, bf = 0, 13, {}
    for g in Tasks:
        bay, proc, obj = g.bay.strip(), g.process.strip(), g.obj.strip() if g.obj else ""
        fill = bf.setdefault(bay, _bay_fill(bay))
        seq += 1
        gs = row
        for i, rt in enumerate(g.requires):
            req = rt.strip()
            for k,v in ctx.items(): req = req.replace(k,v)
            _cell(ws,row,1,seq,font=_F["b"],fill=fill)
            _cell(ws,row,2,bay if i==0 else "",font=_F["b"],fill=fill)
            _cell(ws,row,3,proc if i==0 else "",font=_F["b"],fill=fill)
            _cell(ws,row,4,obj if i==0 else "",font=_F["b"],fill=fill)
            _cell(ws,row,5,req,font=_F["p"],align=_ALIGN_L)
            for c in range(6,14): _cell(ws,row,c,"",font=_F["b"])
            ws.row_dimensions[row].height = max(18,14*max(1,len(req)//40))
            row += 1
        ge = row-1
        if ge>gs:
            for c in (1,2,3,4): ws.merge_cells(start_row=gs,start_column=c,end_row=ge,end_column=c)
    last_row = row-1

    # 页脚: 动态行后 +2 空行
    ft = last_row + 3
    _cell(ws,ft,1,"球面透镜加工工艺卡",font=_F["sec"],fill=_FL["orange"])
    ws.merge_cells(start_row=ft,start_column=1,end_row=ft,end_column=15)
    ws.row_dimensions[ft].height=24
    for c,t in [(1,"产品类型"),(2,"图号"),(3,"工艺卡号"),(10,"版次"),(12,"页次"),(14,"工序\n名称")]:
        _cell(ws,ft+1,c,t,font=_F["h"],fill=_FL["orange"])
    for c,t in [(11,"A"),(13,"1/1"),(15,"总流程")]:
        _cell(ws,ft+1,c,t,font=_F["v"],fill=_FL["orange"])
    ws.row_dimensions[ft+1].height=22
    for c,t in [(1,p.lens_type),(2,p.drawing_no),(3,p.card_no),(10,"制定"),(12,"审核"),(14,"批准")]:
        _cell(ws,ft+2,c,t,font=_F["h"],fill=_FL["orange"])
    for c,v in [(11,p.author),(13,p.reviewer or p.approver),(15,p.approver)]:
        _cell(ws,ft+2,c,v,font=_F["v"],fill=_FL["orange"])
    ws.row_dimensions[ft+2].height=22

    # 列宽
    for l,w in {"A":6,"B":10,"C":12,"D":8,"E":50,"F":14,"G":10}.items():
        ws.column_dimensions[get_column_letter(openpyxl.utils.cell.column_index_from_string(l))].width = w
    for l,w in {"H":12,"I":12,"J":12,"K":14,"L":14,"M":14,"N":12,"O":12,"P":12}.items():
        ws.column_dimensions[get_column_letter(openpyxl.utils.cell.column_index_from_string(l))].width = w

    ws.page_setup.orientation="landscape"; ws.page_setup.fitToWidth=1
    ws.page_setup.fitToHeight=1; ws.sheet_properties.pageSetUpPr=None
    wb.save(filepath)
    return ws.max_row

def export_process_card(filepath: str, lens_params=None, preset_path="manufacturing_process.json"):
    if os.path.exists(preset_path): load_preset(preset_path)
    p = lens_params or LensParams()
    r = calculate(p)
    generate_process_card(filepath, lens_params=p, calc_result=r)
    return r
