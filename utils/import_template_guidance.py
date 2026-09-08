"""设备模板的单元格填写提示；字段名和日期类型复用业务元数据。"""
from datetime import date

from domain_metadata import get_entity_schema

NETWORK_INTERFACE_EXAMPLE = '24个千兆电口、4个千兆光电复用口、4个SFP接口、4个千兆光口、1个CON口、1个S口、1个MGT口、2个USB口'
MEETING_INTERFACE_EXAMPLE = '1个HDMI输入、1个SDI输入、1个卡农头输入、2个DVI输出、1个6.5输出、2个莲花头输出'

DEVICE_INPUT_HINTS = {
    'customer_name': ('选择系统中已有客户的完整名称；不要填写地区名或简称。', '从下拉选择'),
    'device_name': ('填写设备实际名称。同一客户可有同名设备；更新时优先提供设备ID。', '核心交换机'),
    'device_type': ('可从下拉选择，也可自定义填写，最多64个字符。成功导入时自动新增到设备类型设置；同名不重复新增。', '交换机'),
    'brand': ('可从下拉选择，也可自定义填写，最多64个字符。成功导入时自动新增到品牌设置；同名不重复新增。', '华为'),
    'rack_location': ('填写设备所属客户的机房位置，可下拉选择或手填。不要选择其他客户的机房。', '综合楼2楼机房'),
    'rack_name': ('填写机柜号，可下拉选择或手填；与机房、起始U位、占用U数配套填写。', '1'),
    'rack_start_u': ('这里填写设备占用的起始U号，不是结束U号或区间。例如设备占用23-24U，起始U位填23，占用U数填2。只填正整数，不带U。实际范围和冲突由导入预检检查。', '23'),
    'rack_occupy_u': ('这里填写设备占用的U位数量，不是结束U号。例如设备占用23-24U，起始U位填23，占用U数填2，不要填24。只占用23U时填1。只填正整数，不带U。', '2'),
    'location': ('从下拉选择安装面：正面或背面；不是机房地址。', '正面'),
    'power_supply': ('从当前电源配置下拉选择，例如单电源、双电源、四电源；不用于倍增额定功率。', '双电源'),
    'rated_power_w': ('填写整机额定输入功率，单位W，0至10000000的整数；不填W或kW。未知留空，不要填0代替未知。', '300'),
    'ip_address': ('填写IP地址；IPv4使用英文句点，不使用逗号。不在此列拼接端口或网址前缀。', '192.168.1.10'),
    'port': ('填写1至65535的整数；IP和端口分别填写，不填“443端口”。', '443'),
    'network_type': ('从下拉选择当前系统网络类型名称；不要自行使用“内网”等不同名称。', '从下拉选择'),
    'login_method': ('从下拉选择登录方式，支持本地串口；名称与系统设置一致。', '本地串口'),
    'model': ('按文本填写完整型号，保留数字、字母和连接符。', 'S5735-L24T4S-A'),
    'serial_number': ('按文本填写完整序列号，保留前导0；不要让Excel转换为科学计数法。', '001234567890123456'),
    'username': ('按文本填写登录用户名，保留前导0；不填写显示姓名。', 'admin'),
    'password': ('填写实际登录密码；留空永不清除原密码。模板可能含敏感数据，请妥善保管。', '留空可保留原密码'),
    'interface': ('统一按“数量个＋接口类型＋方向”填写，多项用顿号分隔。网络口写明速率和介质，会议接口写明输入或输出；不确定的信息不猜填。详见填写说明中的两类完整示例。', NETWORK_INTERFACE_EXAMPLE),
    'os_version': ('按文本填写完整系统版本，保留版本号中的点号、字母和前导0。', 'V6.0.3.240'),
    'rule_version': ('按文本填写规则库版本；若版本是日期，写2026-08-07，不附加00:00:00。', '2026-08-07'),
    'is_maintenance': ('从下拉选择“是”或“否”。', '否'),
    'is_in_use': ('从下拉选择“是”或“否”。', '是'),
    'device_id': ('更新时填系统导出的设备ID正整数；新增留空。不是Excel行号，不要自行编造。', '从设备批量更新表复制'),
    'remark': ('补充设备说明；日期、端口等信息应填写在各自对应列。', '填写补充说明'),
}

_WHOLE_RULES = {
    'port': ('between', 1, 65535),
    'rack_start_u': ('greaterThanOrEqual', 1, None),
    'rack_occupy_u': ('greaterThanOrEqual', 1, None),
    'device_id': ('greaterThanOrEqual', 1, None),
    'rated_power_w': ('between', 0, 10000000),
}
_TEXT_FIELDS = {
    'rack_name', 'model', 'serial_number', 'ip_address', 'username', 'password',
    'os_version', 'rule_version',
}


def apply_device_template_guidance(ws, fields, last_row=5000):
    """给现有验证补输入提示，不重叠添加验证；返回同源填写说明行。"""
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    date_fields = {f.key for f in get_entity_schema('device').fields if f.data_type == 'date'}
    guide_rows = []
    for col, (label, field) in enumerate(fields, 1):
        letter = get_column_letter(col)
        example = ''
        number_format = None
        if field in date_fields:
            prompt = '格式：YYYY-MM-DD，例如2026-09-05。只填日期，不填时分秒；未知留空。也兼容2026/9/5。'
            example = '2026-09-05'
            validation = DataValidation(type='date', operator='between',
                                        formula1='1', formula2='2958465', allow_blank=True)
            validation.error = '请输入有效日期，例如2026-09-05；不要填写“长期”、备注或不存在的日期。'
            validation.showErrorMessage = True
            number_format = 'yyyy-mm-dd'
            sample = ws.cell(2, col)
            if isinstance(sample.value, str) and sample.value:
                sample.value = date.fromisoformat(sample.value)
        else:
            prompt, example = DEVICE_INPUT_HINTS.get(field, ('按实际信息填写；未知可留空。', ''))
            validation = next((v for v in ws.data_validations.dataValidation
                               if f'{letter}2' in v.sqref), None)
            if validation is None:
                validation = DataValidation(allow_blank=True)
            if field in _WHOLE_RULES:
                operator, lower, upper = _WHOLE_RULES[field]
                validation.type = 'whole'
                validation.operator = operator
                validation.formula1 = str(lower)
                validation.formula2 = str(upper) if upper is not None else None
                validation.showErrorMessage = True
                validation.error = prompt
                number_format = '0'
            elif field in _TEXT_FIELDS:
                number_format = '@'

        validation.promptTitle = label
        validation.prompt = prompt
        validation.showInputMessage = True
        validation.errorTitle = f'{label}填写有误'
        validation.errorStyle = 'stop'
        if validation not in ws.data_validations.dataValidation:
            ws.add_data_validation(validation)
            validation.add(f'{letter}2:{letter}{last_row}')
        if number_format:
            for row in ws.iter_rows(min_row=2, max_row=last_row, min_col=col, max_col=col):
                row[0].number_format = number_format
        ws.cell(2, col).fill = PatternFill('solid', fgColor='FFF2CC')
        guide_rows.append((label, prompt, example))
    ws.freeze_panes = 'C2'
    ws.row_dimensions[1].height = 28
    return guide_rows
