# -*- coding: utf-8 -*-
"""系统运维端点：schema 修复 / drawio 诊断 / 侧栏保存 / 导入模板下载（SSR 业务页已剥离）"""
import os
from datetime import date
from flask import (request, redirect, url_for,
                   flash, jsonify, current_app, abort)
from flask_login import (login_required, current_user)
from models import db, UserDashboardPreference
from utils.permission import admin_required, has_permission
from utils.compat import deprecated_endpoint


# ==================== 简化的 admin 路由（暂留 app.py 后续蓝图化）====================
@login_required
@admin_required
def repair_schema():
    """只读诊断 DB schema；修复必须通过 Alembic 部署命令执行。"""
    from sqlalchemy import inspect as sqla_inspect, text
    reports = []

    # 关键列及其定义（表名 → (列名, SQL 类型)）— 与 models.py / 迁移保持一致
    # 注：用方言无关的 SQLAlchemy 类型生成补列语句（DATETIME 是 SQLite 专属，
    # PG 上必须用 TIMESTAMP，直接写死 DATETIME 会导致 PG 补列失败）
    CRITICAL_COLUMNS = {
        'inspection_tasks': [
            ('estimated_effort', 'FLOAT'),
            ('actual_effort', 'FLOAT'),
        ],
        'topologies': [
            ('diagram_xml', 'TEXT'),
            ('source', 'VARCHAR(16)'),
            ('thumbnail_path', 'VARCHAR(512)'),
            ('pdf_path', 'VARCHAR(512)'),
            ('vsdx_path', 'VARCHAR(512)'),
            ('updated_at', 'DATETIME'),
        ],
    }

    # 1. 当前 alembic 版本
    try:
        insp = sqla_inspect(db.engine)
        if 'alembic_version' not in (insp.get_table_names()):
            reports.append(('alembic_version', '表不存在（遗留库未接入 Alembic）', 'warn'))
        else:
            ver = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()
            reports.append(('alembic 当前版本', ver or '(空)', 'info'))
    except Exception as e:
        reports.append(('alembic 查询失败', str(e), 'danger'))

    # 2. 关键列检查 + 缺失则直接 ALTER TABLE 补列
    try:
        insp = sqla_inspect(db.engine)
        existing_tables = set(insp.get_table_names())
        for tbl, cols_def in CRITICAL_COLUMNS.items():
            if tbl not in existing_tables:
                reports.append((f'{tbl} 表', '❌ 表不存在', 'danger'))
                continue
            existing_cols = {c['name'] for c in insp.get_columns(tbl)}
            for col_name, col_type in cols_def:
                if col_name in existing_cols:
                    reports.append((f'{tbl}.{col_name}', '✅ 存在', 'ok'))
                else:
                    reports.append((f'{tbl}.{col_name}',
                                    f'❌ 缺失（期望类型 {col_type}），请执行迁移', 'danger'))
    except Exception as e:
        reports.append(('列检查失败', str(e), 'danger'))

    # SSR 剥离：返回 JSON（原 render_template 的 repair_schema.html 已下线）
    return jsonify({
        'success': True,
        'reports': [{'name': name, 'status': status, 'detail': detail}
                    for name, detail, status in reports],
        'upgrade_output': [],
    })


@login_required
@admin_required
def drawio_diag():
    """drawio 图标库加载诊断（JSON：clibs 与 stencil 探测结果，替代原诊断页）"""
    import os as _os
    import glob
    from urllib.parse import quote
    stencil_dir = os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'static', 'stencils')
    stencil_urls = []
    clibs = ''
    if _os.path.isdir(stencil_dir):
        stencil_urls = [url_for('static', filename='stencils/' + _os.path.basename(f))
                        for f in sorted(glob.glob(_os.path.join(stencil_dir, '*.drawio.xml')))]
        base = request.host_url.rstrip('/')
        clibs = ';'.join('U' + quote(base + u, safe='') for u in stencil_urls)
    return jsonify({'success': True, 'clibs': clibs, 'stencil_urls': stencil_urls})


@deprecated_endpoint('/api/system/ui-version')
@login_required
@admin_required
def system_ui_version():
    """界面版本切换（兼容遗留 POST；保存后回 SPA 系统概览）"""
    from utils.ui_version import set_ui_version
    version = request.form.get('version')
    if version == 'vue':
        set_ui_version('vue')
        current_app.logger.info('用户 [%s] 确认 Vue 单轨界面', current_user.username)
        flash('系统仅使用 Vue 界面', 'success')
    elif version == 'ssr':
        flash('SSR 已移除，系统仅支持 Vue 界面', 'warning')
    return redirect('/app/system/overview')


    # ==================== 侧栏自定义 ====================
@login_required
def system_sidebar():
    """侧栏自定义（GET 已剥离渲染，302 到 SPA；POST 保留 JSON 保存）"""
    from utils.sidebar_config import save_user_sidebar
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        groups_data = payload.get('groups', [])
        if not isinstance(groups_data, list):
            return jsonify({'success': False, 'message': '参数错误'}), 400
        save_user_sidebar(current_user, groups_data)
        return jsonify({'success': True, 'message': '侧栏设置已保存'})
    return redirect('/app/system/sidebar')


@deprecated_endpoint('/api/system/sidebar/reset')
@login_required
def api_sidebar_reset():
    """重置为默认"""
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if pref:
        pref.sidebar_json = None
        db.session.commit()
    return jsonify({'success': True, 'message': '已重置为系统默认'})


@login_required
def dashboard_reports():
    return redirect('/app/reports')


@login_required
def download_template(module):
    """下载批量导入模板 Excel"""
    import openpyxl
    from copy import deepcopy
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    header_font = Font(name='微软雅黑', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='1890FF', end_color='0969DD', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    from utils.import_templates import get_import_template
    source_tpl = get_import_template(module)
    tpl = deepcopy(source_tpl) if source_tpl else None
    if not tpl:
        abort(404)
    if not has_permission(tpl['permission']):
        return jsonify({'code': 1, 'message': '无权下载该模板'}), 403

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tpl['name']

    for col_idx, h in enumerate(tpl['headers'], 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = max(len(h) * 2.5, 18)

    for col_idx, value in enumerate(tpl.get('example') or [], 1):
        cell = ws.cell(row=2, column=col_idx, value=value)
        cell.alignment = Alignment(vertical='center')
        cell.border = thin_border

    if module == 'customer' and '上级单位' in tpl['headers']:
        from utils.customer_scope import customer_dropdown_options
        values = [item['name'] for item in customer_dropdown_options(current_user)]
        if values:
            dict_ws = wb.create_sheet('数据字典')
            dict_ws.cell(1, 1, '上级单位')
            for row_no, value in enumerate(values, 2):
                dict_ws.cell(row_no, 1, value)
            target_col = tpl['headers'].index('上级单位') + 1
            target_letter = openpyxl.utils.get_column_letter(target_col)
            validation = DataValidation(
                type='list', formula1=f"'数据字典'!$A$2:$A${len(values) + 1}", allow_blank=True)
            ws.add_data_validation(validation)
            validation.add(f'{target_letter}2:{target_letter}5000')
            dict_ws.sheet_state = 'hidden'

    if module == 'device':
        from models import DeviceType, Brand, NetworkType, Rack
        from services.device_service import get_power_supply_choices
        from utils.constants import DEVICE_INSTALLATION_POSITIONS, DEVICE_LOGIN_METHODS
        from utils.customer_scope import customer_dropdown_options

        customer_options = customer_dropdown_options(current_user)
        visible_customer_ids = {item['id'] for item in customer_options}
        dictionaries = {
            '客户': [item['name'] for item in customer_options],
            '类型': [item.name for item in DeviceType.query.order_by(
                DeviceType.sort_order, DeviceType.id).all()],
            '品牌': [item.name for item in Brand.query.order_by(Brand.sort_order, Brand.id).all()],
            '网络类型': [item.name for item in NetworkType.query.order_by(
                NetworkType.sort_order, NetworkType.id).all()],
            '安装位置': list(DEVICE_INSTALLATION_POSITIONS),
            '电源配置': list(get_power_supply_choices()),
            '登录方式': list(DEVICE_LOGIN_METHODS),
            '是否维修': ['是', '否'],
            '是否在用': ['是', '否'],
        }
        rack_query = Rack.query
        if visible_customer_ids:
            rack_query = rack_query.filter(Rack.customer_id.in_(visible_customer_ids))
        else:
            # 当前用户没有可见客户时，模板不能泄露任何机柜名称。
            rack_query = rack_query.filter(Rack.id == -1)
        racks = rack_query.order_by(Rack.name).all()
        dictionaries['机房位置'] = sorted({str(item.location or '').strip() for item in racks
                                             if str(item.location or '').strip()})
        dictionaries['机柜号'] = sorted({str(item.name or '').strip() for item in racks
                                          if str(item.name or '').strip()}, key=lambda value: (len(value), value))

        dict_ws = wb.create_sheet('数据字典')
        for dict_col, (header, values) in enumerate(dictionaries.items(), 1):
            dict_ws.cell(1, dict_col, header)
            clean_values = list(dict.fromkeys(str(value).strip() for value in values
                                               if str(value).strip()))
            for row_no, value in enumerate(clean_values, 2):
                dict_ws.cell(row_no, dict_col, value)
            if not clean_values or header not in tpl['headers']:
                continue
            target_col = tpl['headers'].index(header) + 1
            letter = openpyxl.utils.get_column_letter(dict_col)
            target_letter = openpyxl.utils.get_column_letter(target_col)
            validation = DataValidation(
                type='list',
                formula1=f"'数据字典'!${letter}$2:${letter}${len(clean_values) + 1}",
                allow_blank=True,
                errorTitle='请从下拉列表选择',
                error='该值必须与系统当前设置一致。',
                showErrorMessage=True,
            )
            ws.add_data_validation(validation)
            validation.add(f'{target_letter}2:{target_letter}5000')
            # 示例行也用当前字典，不再硬编码「内网」等历史值。
            ws.cell(2, target_col, clean_values[0])

        if '额定功率' in tpl['headers']:
            target_col = tpl['headers'].index('额定功率') + 1
            target_letter = openpyxl.utils.get_column_letter(target_col)
            validation = DataValidation(type='whole', operator='between', formula1='0',
                                        formula2='10000000', allow_blank=True)
            validation.error = '额定功率请填写非负整数，单位 W。'
            validation.showErrorMessage = True
            ws.add_data_validation(validation)
            validation.add(f'{target_letter}2:{target_letter}5000')
        dict_ws.sheet_state = 'hidden'

        guide = wb.create_sheet('填写说明')
        guide_rows = [
            ('字段/主题', '填写规则'),
            ('示例行', '第 2 行仅用于说明，正式导入前请删除。'),
            ('设备ID（可选）', '系统导出后再导入时优先按设备ID匹配；否则按“客户 + 名称”精确匹配。'),
            ('空值覆盖', '默认空单元格不覆盖原值；只有在导入界面明确勾选“允许空值清除”时才清空。登录密码空白永不清除。'),
            ('机房位置 / 机柜号', '请填写该客户已存在的机房和机柜；机柜、起始U位、占用U数作为一个位置组合校验。'),
            ('起始U位 / 占用U数', '例如起始U位 27、占用U数 4，表示占用 27U-30U；不得超出机柜范围或与其他设备冲突。'),
            ('电源配置', '从下拉选择单电源、双电源或四电源；该字段表示冗余方式，不用于倍增额定功率。'),
            ('额定功率', '填写设备整机额定输入功率，单位 W，仅允许非负整数；不要把多个电源模块铭牌功率简单相加。'),
            ('网络类型', '必须从系统当前网络类型选择；未知值会在预检中聚合提示，确认映射后才可导入。'),
            ('导入模式', '仅新增：已存在则跳过；仅更新：不存在则跳过；新增并更新：不存在新增、存在更新。'),
        ]
        for row in guide_rows:
            guide.append(row)
        guide.column_dimensions['A'].width = 24
        guide.column_dimensions['B'].width = 110
        guide.freeze_panes = 'A2'
        for cell in guide[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
        for row in guide.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.border = thin_border

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    wb.save(tmp.name)
    tmp.close()

    from utils.excel_export import send_temp_export
    return send_temp_export(
        tmp.name, f'{tpl["name"]}_{date.today().isoformat()}.xlsx')
