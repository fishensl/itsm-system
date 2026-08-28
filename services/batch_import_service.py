# -*- coding: utf-8 -*-
"""批量导入服务：备件档案 / 库存 / 巡检记录 / 故障记录（模板列定义见 views/system.download_template）

设计：
- 与「客户导入」（vue_api.py api_v2_customer_import）同款映射模式：按表头列名定位、跳过空行、幂等跳过已存在记录
- 客户按名称匹配（Customer.name）；备件按名称/编码匹配；找不到归属的行计入 errors 不中断
- 返回 (success, errors, skipped)；errors 为每行错误信息列表，供前端展示
"""
from datetime import datetime, date
import re

from models import db, Customer, SparePart, SpareStock, Inspection, Fault
from utils.import_templates import get_import_template


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


def _row_data(ws, row_number, col_map, module):
    """按注册表字段读取一行，确保模板字段不会在导入时被静默忽略。"""
    return {
        field: _cell(ws, row_number, col_map, header)
        for header, field in get_import_template(module)['fields']
    }


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


def _parse_datetime(v):
    """解析 Excel 日期时间；仅给日期时按当天 00:00 保存。"""
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time())
    text = str(v).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# ==================== 备件档案 ====================
def import_spare_parts(ws):
    """导入完整备件可编辑字段（编码唯一，幂等跳过已存在）。"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        row = _row_data(ws, r, col_map, 'spare')
        code = row['code']
        name = row['name']
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
                category=row['category'] or '',
                brand=row['brand'] or '',
                model=row['model'] or '',
                specification=row['specification'] or '',
                unit=row['unit'] or '个',
                min_stock=_int(row['min_stock']) or 0,
                reference_price=_num(row['reference_price']) or 0.0,
                warranty_months=_int(row['warranty_months']) or 0,
                manufacturer=row['manufacturer'] or '',
                serial_number=row['serial_number'] or '',
                remark=row['remark'] or '',
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
        row = _row_data(ws, r, col_map, 'stock')
        pname = row['spare_name']
        if not pname:
            continue
        part = SparePart.query.filter_by(name=pname).first()
        if not part:
            errors.append(f'第{r}行备件「{pname}」不存在，跳过')
            continue
        qty = _int(row['quantity'])
        if qty is None or qty < 0:
            errors.append(f'第{r}行「{pname}」数量无效，跳过')
            continue
        location = row['location'] or ''
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
                unit_price=_num(row['unit_price']) or 0.0,
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{pname}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped


# ==================== 巡检记录 ====================
def import_inspections(ws):
    """导入巡检记录可编辑字段。"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        row = _row_data(ws, r, col_map, 'inspection')
        title = row['title']
        if not title:
            continue
        cust = _find_customer(row['customer_name'])
        if not cust:
            errors.append(f'第{r}行客户「{row["customer_name"]}」不存在，跳过')
            continue
        insp_date = _parse_date(row['inspection_date'])
        status = row['overall_status'] or '正常'
        if status not in ('正常', '警告', '异常'):
            status = '正常'
        try:
            db.session.add(Inspection(
                customer_id=cust.id,
                title=title,
                inspector=row['inspector'] or '',
                inspection_date=insp_date or date.today(),
                location=row['location'] or '',
                overall_status=status,
                conclusion=row['conclusion'] or '',
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{title}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped


# ==================== 故障记录 ====================
def import_faults(ws):
    """导入故障记录可编辑字段；故障分类使用“一级/二级/三级”路径。"""
    col_map = _col_map(ws)
    success = skipped = 0
    errors = []
    for r in range(2, ws.max_row + 1):
        row = _row_data(ws, r, col_map, 'fault')
        title = row['title']
        if not title:
            continue
        cust = _find_customer(row['customer_name'])
        if not cust:
            errors.append(f'第{r}行客户「{row["customer_name"]}」不存在，跳过')
            continue
        ftime = _parse_datetime(row['fault_time'])
        recovery_time = _parse_datetime(row['recovery_time'])
        category_path = [
            item.strip() for item in re.split(r'[/／>＞]+', row['fault_category'])
            if item.strip()
        ][:3]
        category_path.extend([''] * (3 - len(category_path)))
        result = row['result'] or '已解决'
        if result not in ('已解决', '待观察', '未解决'):
            result = '已解决'
        try:
            db.session.add(Fault(
                customer_id=cust.id,
                title=title,
                handler=row['handler'] or '',
                fault_time=ftime or datetime.utcnow(),
                fault_type=row['fault_type'] or '',
                fault_category_level1=category_path[0],
                fault_category_level2=category_path[1],
                fault_category_level3=category_path[2],
                fault_description=row['fault_description'] or '',
                impact_range=row['impact_range'] or '',
                fault_cause=row['fault_cause'] or '',
                solution=row['solution'] or '',
                result=result,
                recovery_time=recovery_time,
            ))
            success += 1
        except Exception as e:
            errors.append(f'第{r}行「{title}」导入失败：{e}')
    db.session.flush()
    return success, errors, skipped
