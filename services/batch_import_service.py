# -*- coding: utf-8 -*-
"""批量导入服务：备件档案 / 库存 / 巡检记录 / 故障记录（模板列定义见 views/system.download_template）

设计：
- 与「客户导入」（vue_api.py api_v2_customer_import）同款映射模式：按表头列名定位、跳过空行、幂等跳过已存在记录
- 客户按名称匹配（Customer.name）；备件按名称/编码匹配；找不到归属的行计入 errors 不中断
- 返回 (success, errors, skipped)；errors 为每行错误信息列表，供前端展示
"""
from datetime import datetime, date

from models import db, Customer, SparePart, SpareStock, Inspection, Fault
from .base import ServiceError


def _col_map(ws):
    """第一行表头 → 列索引（名称去空白）"""
    m = {}
    for i, c in enumerate(ws[1]):
        if c.value:
            m[str(c.value).strip()] = i
    return m


def _cell(ws, r, col_map, name):
    idx = col_map.get(name)
    if idx is None:
        return ''
    v = ws.cell(r, idx + 1).value
    if v is None:
        return ''
    return str(v).strip()


def _num(v):
    """单元格 → float（容忍数字/字符串）"""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _find_customer(name):
    if not name:
        return None
    return Customer.query.filter(Customer.name == name).first()


def _parse_date(v):
    from services.task_schedule_service import parse_excel_date
    if isinstance(v, (datetime, date)):
        return parse_excel_date(v)
    return parse_excel_date(str(v).strip() if v is not None else '')


# ==================== 备件档案 ====================
def import_spare_parts(ws):
    """模板列：编码/名称/分类/规格/单位/最低库存/备注（编码唯一，幂等跳过已存在）"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        code = _cell(ws, r, col_map, '编码')
        name = _cell(ws, r, col_map, '名称')
        if not name:
            continue
        if code and SparePart.query.filter_by(code=code).first():
            skipped += 1
            continue
        if SparePart.query.filter_by(name=name).first():
            skipped += 1
            continue
        try:
            db.session.add(SparePart(
                code=code,
                name=name,
                category=_cell(ws, r, col_map, '分类') or '',
                specification=_cell(ws, r, col_map, '规格') or '',
                unit=_cell(ws, r, col_map, '单位') or '个',
                min_stock=_int(_cell(ws, r, col_map, '最低库存')) or 0,
                remark=_cell(ws, r, col_map, '备注') or '',
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{name}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped


# ==================== 库存 ====================
def import_spare_stocks(ws):
    """模板列：备件名称/位置/数量/单价（按备件名称匹配档案；同名多档案取第一条）"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        pname = _cell(ws, r, col_map, '备件名称')
        if not pname:
            continue
        part = SparePart.query.filter_by(name=pname).first()
        if not part:
            errors.append(f'第{r}行备件「{pname}」不存在，跳过')
            continue
        qty = _int(_cell(ws, r, col_map, '数量'))
        if qty is None or qty < 0:
            errors.append(f'第{r}行「{pname}」数量无效，跳过')
            continue
        location = _cell(ws, r, col_map, '位置') or ''
        # 同名库位已存在则累加（防重复导入翻倍到错误行）
        exist = SpareStock.query.filter_by(spare_part_id=part.id, location=location).first()
        if exist:
            exist.quantity += qty
            skipped += 1
            continue
        try:
            db.session.add(SpareStock(
                spare_part_id=part.id,
                location=location,
                quantity=qty,
                unit_price=_num(_cell(ws, r, col_map, '单价')) or 0.0,
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{pname}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped


# ==================== 巡检记录 ====================
def import_inspections(ws):
    """模板列：客户名称/标题/巡检人员/巡检日期/巡检地点/总体状态/结论/备注"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        title = _cell(ws, r, col_map, '标题')
        if not title:
            continue
        cust = _find_customer(_cell(ws, r, col_map, '客户名称'))
        if not cust:
            errors.append(f'第{r}行客户「{_cell(ws, r, col_map, "客户名称")}」不存在，跳过')
            continue
        insp_date = _parse_date(ws.cell(r, (col_map.get('巡检日期') or 0) + 1).value) \
            if '巡检日期' in col_map else None
        status = _cell(ws, r, col_map, '总体状态') or '正常'
        if status not in ('正常', '警告', '异常'):
            status = '正常'
        try:
            db.session.add(Inspection(
                customer_id=cust.id,
                title=title,
                inspector=_cell(ws, r, col_map, '巡检人员') or '',
                inspection_date=insp_date or date.today(),
                location=_cell(ws, r, col_map, '巡检地点') or '',
                overall_status=status,
                conclusion=_cell(ws, r, col_map, '结论') or '',
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{title}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped


# ==================== 故障记录 ====================
def import_faults(ws):
    """模板列：客户名称/标题/处理人/故障时间/故障类型/故障描述/故障原因/解决方案/处理结果"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        title = _cell(ws, r, col_map, '标题')
        if not title:
            continue
        cust = _find_customer(_cell(ws, r, col_map, '客户名称'))
        if not cust:
            errors.append(f'第{r}行客户「{_cell(ws, r, col_map, "客户名称")}」不存在，跳过')
            continue
        ftime = _parse_date(ws.cell(r, (col_map.get('故障时间') or 0) + 1).value) \
            if '故障时间' in col_map else None
        result = _cell(ws, r, col_map, '处理结果') or '已解决'
        if result not in ('已解决', '待观察', '未解决'):
            result = '已解决'
        try:
            db.session.add(Fault(
                customer_id=cust.id,
                title=title,
                handler=_cell(ws, r, col_map, '处理人') or '',
                fault_time=datetime.combine(ftime, datetime.min.time()) if ftime else datetime.utcnow(),
                fault_type=_cell(ws, r, col_map, '故障类型') or '',
                fault_description=_cell(ws, r, col_map, '故障描述') or '',
                fault_cause=_cell(ws, r, col_map, '故障原因') or '',
                solution=_cell(ws, r, col_map, '解决方案') or '',
                result=result,
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{title}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped
