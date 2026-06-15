"""Word 报告自动生成模块"""
import os
import logging
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from flask import current_app


def _chinese_uppercase_date(d):
    """将日期转为中文大写，如 2026-05-21 → 二〇二六年五月二十一日"""
    digits = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九']
    months = ['一月', '二月', '三月', '四月', '五月', '六月',
              '七月', '八月', '九月', '十月', '十一月', '十二月']
    # 日期的特殊写法
    def _day_str(day):
        if day < 1 or day > 31:
            return str(day)
        if day <= 10:
            if day == 10:
                return '十日'
            return digits[day] + '日'
        elif day < 20:
            prefix = '十'
            unit = day % 10
            if unit == 0:
                return '十日'
            return prefix + digits[unit] + '日'
        elif day == 20:
            return '二十日'
        elif day < 30:
            return '二十' + digits[day % 10] + '日'
        elif day == 30:
            return '三十日'
        else:
            return '三十一' if day == 31 else '三十' + digits[day % 10] + '日'

    year_str = ''.join(digits[int(ch)] for ch in f'{d.year:04d}') + '年'
    month_str = months[d.month - 1]
    day_str = _day_str(d.day)
    return year_str + month_str + day_str


def _set_run_font(run, font_name='宋体', size_pt=10, bold=False, color=None):
    """设置 run 的字体属性"""
    run.font.size = Pt(size_pt)
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    if bold:
        run.bold = True
    if color:
        run.font.color.rgb = color


def _set_cell_text(cell, text, bold=False, size=10, align=WD_ALIGN_PARAGRAPH.LEFT):
    """设置表格单元格文本"""
    cell.text = ''
    p = cell.paragraphs[0]
    p.alignment = align
    run = p.add_run(str(text))
    run.font.size = Pt(size)
    run.font.name = '宋体'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    if bold:
        run.bold = True


def _add_table_row(table, cells_data, bold=False, header=False):
    """添加表格行"""
    row = table.add_row()
    for i, val in enumerate(cells_data):
        if i < len(row.cells):
            _set_cell_text(row.cells[i], val, bold=bold)
    return row


def _add_chapter_heading(doc, number, title):
    """添加章节标题（Heading 2 样式，宋体三号16pt，黑色）"""
    p = doc.add_heading(f'{number}、{title}', level=2)
    for run in p.runs:
        run.font.name = '宋体'
        run.font.size = Pt(16)
        run.bold = True
        run.font.color.rgb = RGBColor(0, 0, 0)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    return p


def _add_sub_heading(doc, num, title):
    """添加子章节标题（Heading 3 样式，宋体四号14pt加粗，黑色）"""
    p = doc.add_heading(f'{num} {title}', level=3)
    for run in p.runs:
        run.font.name = '宋体'
        run.font.size = Pt(14)
        run.bold = True
        run.font.color.rgb = RGBColor(0, 0, 0)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')


def _add_toc(doc, chapters):
    """添加目录页（Word 自动目录 TOC 域）"""
    from docx.oxml import OxmlElement
    for _ in range(3):
        doc.add_paragraph()
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_title.add_run('目  录')
    _set_run_font(run, font_name='宋体', size_pt=22, bold=True)
    doc.add_paragraph()

    # 插入 Word TOC 域代码（基于 Heading 1-3 样式）
    p = doc.add_paragraph()
    p.paragraph_format.tab_stops.add_tab_stop(Inches(6.0))

    def _add_toc_field(prg, code, text):
        r1 = prg.add_run()
        fc1 = OxmlElement('w:fldChar')
        fc1.set(qn('w:fldCharType'), 'begin')
        r1._element.append(fc1)
        r2 = prg.add_run()
        it = OxmlElement('w:instrText')
        it.set(qn('xml:space'), 'preserve')
        it.text = code
        r2._element.append(it)
        r3 = prg.add_run()
        fc2 = OxmlElement('w:fldChar')
        fc2.set(qn('w:fldCharType'), 'separate')
        r3._element.append(fc2)
        r4 = prg.add_run(text)
        r4.font.color.rgb = RGBColor(128, 128, 128)
        r4.font.size = Pt(12)
        r5 = prg.add_run()
        fc3 = OxmlElement('w:fldChar')
        fc3.set(qn('w:fldCharType'), 'end')
        r5._element.append(fc3)

    _add_toc_field(p, r' TOC \o "1-3" \h \z \u ', '【右键此处 → 更新域 → 更新整个目录，页码自动生成】')
    doc.add_page_break()


def _add_section_photos(doc, sections, key):
    """在章节中插入照片"""
    photos = sections.get(f'{key}_photos', [])
    if photos:
        for photo_path in photos:
            full_path = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path))
            if os.path.exists(full_path):
                try:
                    doc.add_picture(full_path, width=Inches(3.0))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                except Exception:
                    pass


def generate_inspection_report(inspection, customer_name, devices_content, sections=None, field_values=None):
    """生成巡检报告 Word 文档

    Args:
        inspection: Inspection 对象
        customer_name: 客户名称
        devices_content: 设备检查内容
        sections: 报告章节
        field_values: 自定义字段值 {"设备名": {"检查项": "值"}}

    Returns:
        生成的报告文件路径
    """
    # V3: 审核状态检查 - 只有审核通过后才可生成报告
    review_status = getattr(inspection, 'review_status', '')
    if review_status and review_status not in ('已通过', ''):
        # 未审核通过时不阻止，但标记
        pass  # 允许但可以加水印或提示

    if sections is None:
        sections = {}
    if field_values is None:
        field_values = {}
    doc = Document()
    date_cn = _chinese_uppercase_date(
        inspection.inspection_date if hasattr(inspection.inspection_date, 'year') else datetime.now().date()
    )

    chapters = [
        ('一', '基本信息'),
        ('二', '季度运维工作内容'),
        ('三', '巡检记录表'),
        ('四', '网络拓扑图'),
        ('五', '设备台账'),
        ('六', '防汛网络运行建议'),
        ('七', '售后服务电话及联系人'),
    ]

    # ========== 封面 ==========
    for _ in range(5):
        doc.add_paragraph()

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_text = f'{customer_name}{inspection.title}报告'
    run = p_title.add_run(title_text)
    _set_run_font(run, font_name='宋体', size_pt=26, bold=False)

    for _ in range(11):
        p_sp = doc.add_paragraph()
        p_sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sp = p_sp.add_run('')
        _set_run_font(run_sp, font_name='宋体', size_pt=14)

    p_company = doc.add_paragraph()
    p_company.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_company.add_run('江西丰功信息技术有限公司')
    _set_run_font(run, font_name='宋体', size_pt=16, bold=False)

    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_date.add_run(date_cn)
    _set_run_font(run, font_name='宋体', size_pt=16, bold=False)

    doc.add_page_break()

    # ========== 目录 ==========
    # 目录后加 section 分节符，从此页起显示页码
    from docx.enum.section import WD_ORIENT
    from docx.oxml import OxmlElement
    new_section = doc.add_section()
    new_section.top_margin = Cm(2.5)
    new_section.bottom_margin = Cm(2.5)
    new_section.left_margin = Cm(2.5)
    new_section.right_margin = Cm(2.5)
    # 添加页脚页码
    footer = new_section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 插入页码域
    run_page = fp.add_run()
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    run_page._element.append(fldChar1)
    run_page2 = fp.add_run()
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' PAGE '
    run_page2._element.append(instrText)
    run_page3 = fp.add_run()
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'end')
    run_page3._element.append(fldChar2)

    # ========== 一、基本信息 ==========
    _add_chapter_heading(doc, '一', '基本信息')
    # V13: 加入"联系电话"行 — 6 行 → 7 行
    inspector_name = inspection.inspector_name or inspection.inspector or ''
    inspector_phone = inspection.inspector_phone or ''
    info_table = doc.add_table(rows=7, cols=2)
    info_table.style = 'Table Grid'
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    rows_data = [
        ('客户名称', customer_name),
        ('巡检地点', inspection.location or customer_name),
        ('巡检人员', inspector_name),
        ('联系电话', inspector_phone or '-'),
        ('巡检日期', date_cn),
        ('巡检标题', inspection.title),
        ('总体状态', inspection.overall_status),
    ]
    for idx, (k, v) in enumerate(rows_data):
        _set_cell_text(info_table.rows[idx].cells[0], k, bold=True, size=14)
        _set_cell_text(info_table.rows[idx].cells[1], v, size=14)
    doc.add_paragraph()

    # ========== 二、季度运维工作内容 ==========
    _add_chapter_heading(doc, '二', '季度运维工作内容')

    _add_sub_heading(doc, '2.1', '季度巡检')
    doc.add_paragraph(sections.get('q2_1', '（请在此处填写季度巡检工作情况）'))
    doc.add_paragraph()

    _add_sub_heading(doc, '2.2', '机房环境检查')
    doc.add_paragraph(sections.get('q2_2', '（请在此处填写机房环境检查情况）'))
    doc.add_paragraph()

    _add_sub_heading(doc, '2.3', '设备配置备份')
    doc.add_paragraph(sections.get('q2_3', '（请在此处填写设备配置备份情况）'))
    _add_section_photos(doc, sections, 'q2_3')
    doc.add_paragraph()

    _add_sub_heading(doc, '2.4', '标签及线缆检查')
    doc.add_paragraph(sections.get('q2_4', '（请在此处填写标签及线缆检查情况）'))
    _add_section_photos(doc, sections, 'q2_4')

    # ========== 三、巡检记录表 ==========
    _add_chapter_heading(doc, '三', '巡检记录表')
    for dev_idx, dc in enumerate(devices_content, 1):
        device_name = dc.get('device', '未知设备')
        _add_sub_heading(doc, f'3.{dev_idx}', device_name)

        items = dc.get('items', [])
        photos = dc.get('photos', [])
        total_rows = 7 + (1 if items else 0) + len(items) + len(photos)
        tbl = doc.add_table(rows=total_rows, cols=3)
        tbl.style = 'Table Grid'

        info_rows = [
            ('设备名称', device_name),
            ('设备类型', dc.get('type', '') or '-'),
            ('设备型号', dc.get('model', '') or '-'),
            ('安装位置', dc.get('location', '') or '-'),
            ('IP地址', dc.get('ip', '') or '-'),
            ('系统版本', dc.get('os_version', '') or '-'),
            ('系统运行时间', dc.get('uptime', '') or '-'),
        ]
        for idx, (k, v) in enumerate(info_rows):
            _set_cell_text(tbl.rows[idx].cells[0], k, bold=True, size=9)
            _set_cell_text(tbl.rows[idx].cells[1], v, size=9)
            tbl.rows[idx].cells[1].merge(tbl.rows[idx].cells[2])

        row_idx = 7
        if items:
            headers = ['检查项', '结果', '备注']
            for i, h in enumerate(headers):
                _set_cell_text(tbl.rows[row_idx].cells[i], h, bold=True, size=10)
            row_idx += 1
            for item in items:
                _set_cell_text(tbl.rows[row_idx].cells[0], item.get('name', ''), size=10.5)
                result = item.get('result', '')
                _set_cell_text(tbl.rows[row_idx].cells[1], result, size=10.5)
                if result == '异常':
                    tbl.rows[row_idx].cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 0, 0)
                _set_cell_text(tbl.rows[row_idx].cells[2], item.get('remark', ''), size=10.5)
                row_idx += 1

        for p_idx, photo_path in enumerate(photos):
            cell = tbl.rows[row_idx].cells[0]
            cell.merge(tbl.rows[row_idx].cells[1]).merge(tbl.rows[row_idx].cells[2])
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(f'【现场照片 {p_idx + 1}】')
            _set_run_font(run, size_pt=9, bold=True)
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path)
            if os.path.exists(full_path):
                p2 = cell.add_paragraph()
                p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p2.add_run().add_picture(full_path, width=Inches(3.0))
            row_idx += 1
        doc.add_paragraph()

    # ========== 四、网络拓扑图 ==========
    _add_chapter_heading(doc, '四', '网络拓扑图')
    doc.add_paragraph(sections.get('network_topology', '（请在此处填写网络拓扑情况）'))
    topo_photos = sections.get('topology_photos', [])
    if topo_photos:
        doc.add_paragraph()
        for photo_path in topo_photos:
            try:
                full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path)
                if os.path.exists(full_path):
                    doc.add_picture(full_path, width=Inches(4.0))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                pass

    # ========== 五、设备台账（自动调用设备管理信息）==========
    _add_chapter_heading(doc, '五', '设备台账')
    if devices_content:
        ledger_tbl = doc.add_table(rows=1 + len(devices_content), cols=6)
        ledger_tbl.style = 'Table Grid'
        ledger_headers = ['设备名称', '设备类型', '设备型号', 'IP地址', '系统版本', '安装位置']
        for i, h in enumerate(ledger_headers):
            _set_cell_text(ledger_tbl.rows[0].cells[i], h, bold=True, size=10)
        for idx, dc in enumerate(devices_content):
            row = ledger_tbl.rows[1 + idx]
            _set_cell_text(row.cells[0], dc.get('device', ''))
            _set_cell_text(row.cells[1], dc.get('type', '') or '-')
            _set_cell_text(row.cells[2], dc.get('model', '') or '-')
            _set_cell_text(row.cells[3], dc.get('ip', '') or '-')
            _set_cell_text(row.cells[4], dc.get('os_version', '') or '-')
            _set_cell_text(row.cells[5], dc.get('location', '') or '-')
    extra_ledger = sections.get('device_ledger', '')
    if extra_ledger:
        doc.add_paragraph()
        doc.add_paragraph(extra_ledger)

    # ========== 六、防汛网络运行建议 ==========
    _add_chapter_heading(doc, '六', '防汛网络运行建议')
    doc.add_paragraph(sections.get('flood_advice', '（请在此处填写防汛网络运行建议）'))

    # ========== 七、售后服务电话及联系人 ==========
    _add_chapter_heading(doc, '七', '售后服务电话及联系人')
    tech_support = sections.get('tech_support', '')
    complaint = sections.get('complaint', '')
    owner_sign = sections.get('owner_sign', '')

    for txt in [f'技术支持：{tech_support}' if tech_support else '技术支持：',
                f'投诉与建议：{complaint}' if complaint else '投诉与建议：',
                f'业主签字：{owner_sign}' if owner_sign else '业主签字：']:
        p = doc.add_paragraph(txt)
        p.paragraph_format.first_line_indent = Pt(28)
        _set_run_font(p.runs[0], size_pt=14)
    # 运维公司 + 印章（印章衬于文字下方）
    seal_image = sections.get('seal_image', '')
    p_company = doc.add_paragraph()
    p_company.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_company.paragraph_format.space_before = Pt(0)
    p_company.paragraph_format.space_after = Pt(0)
    run_company = p_company.add_run('运维公司：江西丰功信息技术有限公司')
    _set_run_font(run_company, size_pt=16)
    if seal_image:
        full_path = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), seal_image))
        r_seal = p_company.add_run()
        r_seal.add_picture(full_path, width=Cm(4.0))
    # 报告日期
    report_date_str = inspection.inspection_date.strftime('%Y年%m月%d日') if hasattr(inspection.inspection_date, 'strftime') else datetime.now().strftime('%Y年%m月%d日')
    p_date = doc.add_paragraph(f'报告生成日期：{report_date_str}')
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_date.paragraph_format.space_before = Pt(0)
    if p_date.runs:
        _set_run_font(p_date.runs[0], size_pt=16)

    # 保存
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    filename = f'巡检报告_{inspection.title}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.docx'
    filepath = os.path.join(reports_dir, filename)
    doc.save(filepath)
    return filepath


def generate_fault_report(fault, customer_name):
    """生成故障处理报告 Word 文档"""
    doc = Document()

    # ========== 封面（参照巡检报告格式）==========
    for _ in range(5):
        doc.add_paragraph()

    # 主标题：客户名称 + 故障标题 + 故障处理报告  宋体一号(26pt) 居中
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_text = f'{customer_name}{fault.title}故障处理报告'
    run = p_title.add_run(title_text)
    _set_run_font(run, font_name='宋体', size_pt=26, bold=False)

    # 空11行（四号字14pt行距）
    for _ in range(11):
        p_sp = doc.add_paragraph()
        p_sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sp = p_sp.add_run('')
        _set_run_font(run_sp, font_name='宋体', size_pt=14)

    # 公司名称：宋体三号(16pt) 居中
    p_company = doc.add_paragraph()
    p_company.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_company.add_run('江西丰功信息技术有限公司')
    _set_run_font(run, font_name='宋体', size_pt=16, bold=False)

    # 日期：中文大写 宋体三号(16pt) 居中
    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_cn = _chinese_uppercase_date(
        fault.fault_time if hasattr(fault.fault_time, 'year') else datetime.now().date()
    )
    run = p_date.add_run(date_cn)
    _set_run_font(run, font_name='宋体', size_pt=16, bold=False)

    # 封面后分页
    doc.add_page_break()

    # ========== 正文 ==========
    # 基本信息
    info_table = doc.add_table(rows=9, cols=2)
    info_table.style = 'Table Grid'
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    fault_time_str = fault.fault_time.strftime('%Y-%m-%d %H:%M') if hasattr(fault.fault_time, 'strftime') else str(fault.fault_time)
    recovery_time_str = (fault.recovery_time.strftime('%Y-%m-%d %H:%M') if hasattr(fault.recovery_time, 'strftime') else str(fault.recovery_time)) if fault.recovery_time else '—'

    rows_data = [
        ('客户名称', customer_name),
        ('故障标题', fault.title),
        ('处理人员', fault.handler),
        ('故障时间', fault_time_str),
        ('故障类型', fault.fault_type),
        ('影响范围', fault.impact_range),
        ('处理结果', fault.result),
        ('恢复时间', recovery_time_str),
    ]
    for idx, (k, v) in enumerate(rows_data):
        _set_cell_text(info_table.rows[idx].cells[0], k, bold=True)
        _set_cell_text(info_table.rows[idx].cells[1], v)

    doc.add_paragraph()

    # 故障描述
    h1 = doc.add_heading('', level=1)
    run = h1.add_run('一、故障描述')
    run.font.color.rgb = RGBColor(180, 0, 0)
    doc.add_paragraph(fault.fault_description or '无。')

    doc.add_paragraph()

    # 故障原因
    h2 = doc.add_heading('', level=1)
    run = h2.add_run('二、故障原因分析')
    run.font.color.rgb = RGBColor(180, 0, 0)
    doc.add_paragraph(fault.fault_cause or '待进一步分析。')

    doc.add_paragraph()

    # 解决方案
    h3 = doc.add_heading('', level=1)
    run = h3.add_run('三、解决方案')
    run.font.color.rgb = RGBColor(180, 0, 0)
    doc.add_paragraph(fault.solution or '无。')

    doc.add_paragraph()

    # 底部
    doc.add_paragraph(f'报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    doc.add_paragraph(f'处理人员：{fault.handler}')

    # 保存
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    filename = f'故障报告_{fault.title}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.docx'
    filepath = os.path.join(reports_dir, filename)
    doc.save(filepath)
    return filepath


# ============================
# V4: 9章固定结构巡检报告生成器
# ============================

def generate_inspection_report_v4(inspection, customer_name, device_results=None, sections=None):
    """按固定9章结构生成巡检报告（V4复合巡检）。参见模块文档了解完整参数说明。"""
    import json

    if sections is None:
        sections = {}
    if device_results is None:
        device_results = []
    if not device_results and inspection:
        try:
            fv = json.loads(inspection.field_values_json) if isinstance(inspection.field_values_json, str) else (inspection.field_values_json or {})
            device_results = _build_device_results_from_values(inspection, fv)
        except:
            pass

    doc = Document()
    date_cn = _chinese_uppercase_date(
        inspection.inspection_date if hasattr(inspection, 'inspection_date') and inspection.inspection_date and hasattr(inspection.inspection_date, 'year') else datetime.now().date()
    )

    # 封面
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f'{customer_name}网络巡检运维服务报告')
    _set_run_font(run, '宋体', 28, bold=True)
    doc.add_paragraph()
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run('江西丰功信息技术有限公司')
    _set_run_font(run2, '宋体', 22, bold=True)
    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = p3.add_run(date_cn)
    _set_run_font(run3, '宋体', 18)
    doc.add_page_break()

    # 目录
    _add_toc(doc, ['总体情况', '季度运维工作内容', '巡检记录表', '现场图片', '故障工单', '网络拓扑图', '设备台账', '网络运行建议', '售后服务电话'])

    # === Ch1: 总体情况 ===
    _add_chapter_heading(doc, '一', '总体情况')
    doc.add_paragraph(f'本次机房巡检工作于{date_cn}全面展开。')
    _add_sub_heading(doc, '1.1', '运维对象')
    doc.add_paragraph('▸ 机房')
    if device_results:
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = 'Table Grid'
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _add_table_row(tbl, ['序号', '项目', 'IP地址', '管辖', '运行态势'], bold=True, header=True)
        for idx, dr in enumerate(device_results, 1):
            status = '运行良好'
            for item in dr.get('items', []):
                if item.get('value', '') in ('不正常', '异常', '低于标准', '已过期'):
                    status = '故障'
                    break
            _add_table_row(tbl, [str(idx), dr.get('device_name', '-'), dr.get('ip_address', '-'), customer_name, status])
        doc.add_paragraph()

    _add_sub_heading(doc, '1.2', '防汛机房情况汇报')
    doc.add_paragraph(sections.get('q1_2', ''))

    _add_sub_heading(doc, '1.3', '现场巡检隐患清单')
    doc.add_paragraph('根据现场巡检及日常运维发现以下隐患：')
    abnormal_items = []
    for dr in device_results:
        for item in dr.get('items', []):
            val = item.get('value', '')
            if val in ('不正常', '异常', '低于标准', '已过期', '即将到期'):
                abnormal_items.append({'cat': dr.get('template_category', ''), 'dev': dr.get('device_name', ''), 'item': item.get('name', ''), 'status': val})
    if abnormal_items:
        tbl2 = doc.add_table(rows=1, cols=5)
        tbl2.style = 'Table Grid'
        tbl2.alignment = WD_TABLE_ALIGNMENT.CENTER
        _add_table_row(tbl2, ['序号', '项目', '子项', '巡检情况', '备注'], bold=True, header=True)
        for idx, a in enumerate(abnormal_items, 1):
            _add_table_row(tbl2, [str(idx), a['cat'], f'{a["dev"]}-{a["item"]}', a['status'], ''])
    else:
        doc.add_paragraph('本次巡检未发现安全隐患。')

    _add_sub_heading(doc, '1.4', '隐患详情及影响')
    try:
        sr = json.loads(inspection.skip_reasons_json) if isinstance(inspection.skip_reasons_json, str) else (inspection.skip_reasons_json or {})
    except Exception as _e:
        current_app.logger.warning('解析 skip_reasons_json 失败：%s', repr(_e))
        sr = {}
    issue_idx = 1
    for dev_key, dev_sr in sr.items():
        if isinstance(dev_sr, dict):
            for item_name, reason_info in dev_sr.items():
                reason = reason_info.get('reason', '') if isinstance(reason_info, dict) else str(reason_info)
                detail = reason_info.get('detail', '') if isinstance(reason_info, dict) else ''
                if reason:
                    doc.add_paragraph(f'{issue_idx}、{dev_key} -- {item_name}')
                    doc.add_paragraph(f'   隐患内容：{reason}')
                    if detail:
                        doc.add_paragraph(f'   详情：{detail}')
                    issue_idx += 1
    if issue_idx == 1:
        doc.add_paragraph('本次巡检未发现重大隐患。')

    # === Ch2: 季度运维工作 ===
    _add_chapter_heading(doc, '二', '季度运维工作内容')
    for sub, title in [('q2_1', '季度巡检'), ('q2_2', '机房环境检查'), ('q2_3', '网络设备配置备份'),
                        ('q2_4', '标签及线缆检查'), ('q2_5', '核心交换机空接口做shutdown处理')]:
        _add_sub_heading(doc, sub.replace('q', '').replace('_', '.'), title)
        doc.add_paragraph(sections.get(sub, ''))
        if sub in ('q2_3', 'q2_4'):
            _add_section_photos(doc, sections, sub.replace('q', ''))

    # === Ch3: 巡检记录表 ===
    _add_chapter_heading(doc, '三', '巡检记录表')
    cat_order = {'服务器': 0, '网络设备': 1, '安全设备': 2, 'UPS': 3, '空调': 4}
    sorted_devices = sorted(device_results, key=lambda d: cat_order.get(d.get('template_category', ''), 99))
    counters = {}
    base_nums = {'服务器': '3.1', '网络设备': '3.2', '安全设备': '3.5', 'UPS': '3.12', '空调': '3.13'}

    for dr in sorted_devices:
        cat = dr.get('template_category', '其他')
        counters[cat] = counters.get(cat, 0) + 1
        idx = counters[cat]
        base = base_nums.get(cat, '3.1')
        try:
            parts = base.split('.')
            sec_num = f'{parts[0]}.{int(parts[1]) + idx - 1}'
        except:
            sec_num = f'3.{idx}'
        _add_sub_heading(doc, f'{sec_num}．', f'{cat}巡检记录表-{idx}')

        # 设备信息头表
        info_t = doc.add_table(rows=4, cols=2)
        info_t.style = 'Table Grid'
        info_t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for (k1, v1, k2, v2), row_idx in zip([
            ('设备名称', dr.get('device_name', '-'), '安装位置', dr.get('location', '-')),
            ('设备型号', dr.get('model', '-'), '管理IP地址', dr.get('ip_address', '-')),
            ('操作系统版本', dr.get('os_version', '-'), '系统运行时间', dr.get('uptime', '-')),
            ('匹配模板', dr.get('template_name', '-'), '设备类型', dr.get('device_type', '-')),
        ], range(4)):
            _set_cell_text(info_t.rows[row_idx].cells[0], f'{k1}: {v1}')
            _set_cell_text(info_t.rows[row_idx].cells[1], f'{k2}: {v2}')
        doc.add_paragraph()

        # 检查项表（5列）
        items = dr.get('items', [])
        if items:
            chk_t = doc.add_table(rows=1, cols=5)
            chk_t.style = 'Table Grid'
            chk_t.alignment = WD_TABLE_ALIGNMENT.CENTER
            _add_table_row(chk_t, ['序号', '巡检内容', '检查项目说明', '巡检情况说明', '备注'], bold=True, header=True)
            for item_idx, item in enumerate(items, 1):
                name = item.get('name', '')
                help_txt = item.get('help_text', '')
                val = item.get('value', '-')
                ft = item.get('field_type', 'text')
                if ft == 'dropdown':
                    if val in ('正常', '符合要求'):
                        disp = '☑ 正常 □ 其他'
                    else:
                        disp = f'□ 正常 ☑ {val}'
                else:
                    disp = str(val)
                _add_table_row(chk_t, [str(item_idx), name, help_txt, disp, ''])
        doc.add_paragraph()

    # === Ch4-9 ===
    _add_chapter_heading(doc, '四', '现场图片')
    doc.add_paragraph(sections.get('q4_images', '（暂无现场图片）'))
    _add_chapter_heading(doc, '五', '故障工单')
    doc.add_paragraph('无')
    _add_chapter_heading(doc, '六', '网络拓扑图')
    topology_photos = sections.get('topology_photos', [])
    if topology_photos:
        for tp in topology_photos:
            if os.path.exists(tp.lstrip('/')):
                try:
                    doc.add_picture(tp.lstrip('/'), width=Inches(5.0))
                except:
                    pass
    _add_chapter_heading(doc, '七', '设备台账')
    if device_results:
        ldr_t = doc.add_table(rows=1, cols=5)
        ldr_t.style = 'Table Grid'
        ldr_t.alignment = WD_TABLE_ALIGNMENT.CENTER
        _add_table_row(ldr_t, ['序号', '设备名称', '设备型号', '管理IP', '位置'], bold=True, header=True)
        for idx, dr in enumerate(device_results, 1):
            _add_table_row(ldr_t, [str(idx), dr.get('device_name', '-'), dr.get('model', '-'), dr.get('ip_address', '-'), dr.get('location', '-')])
    doc.add_paragraph()
    _add_chapter_heading(doc, '八', '网络运行建议')
    doc.add_paragraph(sections.get('flood_advice', ''))
    _add_chapter_heading(doc, '九', '售后服务电话')
    doc.add_paragraph(f'运维工程师 {sections.get("tech_support", "")}')
    doc.add_paragraph(f'业务经理 {sections.get("complaint", "")}')
    doc.add_paragraph(f'业主签字：{sections.get("owner_sign", "")}')
    doc.add_paragraph('运维公司：江西丰功信息技术有限公司')
    doc.add_paragraph(f'报告生成日期：{datetime.now().strftime("%Y年%m月%d日")}')
    seal = sections.get('seal_image', '')
    if seal and os.path.exists(seal.lstrip('/')):
        try:
            doc.add_picture(seal.lstrip('/'), width=Inches(1.5))
        except:
            pass

    # 保存
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    title_safe = inspection.title.replace('/', '_').replace('\\', '_')[:50] if inspection and inspection.title else '巡检'
    filename = f'巡检报告_{title_safe}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.docx'
    filepath = os.path.join(reports_dir, filename)
    doc.save(filepath)
    return filepath


def _build_device_results_from_values(inspection, field_values):
    """从 field_values_json 和 Device 表重建 device_results"""
    from models import Device
    results = []
    if not field_values:
        return results
    for dev_key, items_dict in field_values.items():
        if not isinstance(items_dict, dict):
            continue
        device = Device.query.filter_by(device_name=dev_key).first()
        cat = _infer_device_category(device.device_type) if device else '其他'
        items_list = []
        for item_name, item_value in items_dict.items():
            if item_name == '系统运行时间':
                continue
            items_list.append({'name': item_name, 'value': str(item_value) if item_value else '', 'field_type': 'text', 'help_text': ''})
        results.append({
            'device_name': dev_key, 'device_type': device.device_type if device else '',
            'location': device.location if device else '', 'model': device.model if device else '',
            'ip_address': device.ip_address if device else '', 'os_version': device.os_version if device else '',
            'uptime': items_dict.get('系统运行时间', '-'), 'template_name': f'{cat}通用巡检',
            'template_category': cat, 'items': items_list, 'summary': '', 'photos': [],
        })
    return results


def _infer_device_category(device_type):
    dt = (device_type or '').lower()
    if any(k in dt for k in ['服务器', 'server']): return '服务器'
    if any(k in dt for k in ['交换机', '路由器', 'switch', 'router']): return '网络设备'
    if any(k in dt for k in ['防火墙', 'ips', 'ids', 'waf', 'vpn', '上网行为']): return '安全设备'
    if any(k in dt for k in ['ups', '电源']): return 'UPS'
    if any(k in dt for k in ['空调', '精密空调']): return '空调'
    return '其他'
