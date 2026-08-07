# -*- coding: utf-8 -*-
"""丰功信息网络拓扑模板生成脚本（等保三级「一个中心三重防护」通用模板）。

按《网络拓扑、会议系统与数据流图绘制规范》生成 drawio 文件：
- 区域分层：互联网出口 → 边界防护 → 核心交换 → 业务服务器区/核心数据区/安全管理区/办公接入区
- 线型规范 §3.4：深蓝业务流 #0050EF 2.5pt 实心箭头 / 黑物理网线 / 橙光纤 / 灰管理虚线 / 紫 LACP / 浅灰备用
- 设备标注 §6.2 双行（中文名黑体加粗 + 代码 Consolas）+ 型号/IP
- 图例 §8（设备图标图例 + 线缆图例） + 标题栏 §2.4 + 字体 §6.1

用法（项目根目录）：
    python scripts/build_templates.py
"""
import os
import sys
import xml.sax.saxutils as sax

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'static', 'templates', 'template-network-topology.drawio')

PAGE_W, PAGE_H = 1400, 1080

BLUE = '#0050EF'      # 业务数据流
BLACK = '#333333'     # 物理网线
ORANGE = '#FF6600'    # 光纤互联
GRAY = '#666666'      # 管理维护流
PURPLE = '#9B59B6'    # 链路聚合 LACP
LGRAY = '#CCCCCC'     # 备用/未启用

C_NET = '#EAF0FF'     # 网络设备
C_SEC = '#FFF3E6'     # 安全设备
C_SVR = '#E8F7EE'     # 服务器
C_DB = '#F3EBFF'      # 数据库/存储
C_CLI = '#F5F5F5'     # 客户端

_counter = [0]


def nid():
    _counter[0] += 1
    return f'c{_counter[0]}'


def esc(s):
    return sax.escape(s, {'"': '&quot;'})


def cell(value, style, x, y, w, h, edge=False, source=None, target=None):
    cid = nid()
    value = esc(value) if value else ''
    if edge:
        return cid, (f'<mxCell id="{cid}" value="{value}" style="{style}" edge="1" parent="1" '
                     f'source="{source}" target="{target}">'
                     f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    return cid, (f'<mxCell id="{cid}" value="{value}" style="{style}" vertex="1" parent="1">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def region(x, y, w, h, title, subtitle='', fill='#F8FAFF'):
    value = f'<b>{esc(title)}</b>'
    if subtitle:
        value += f'<br><font color="#999999" style="font-size:10px">{esc(subtitle)}</font>'
    style = ('rounded=0;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;'
             f'strokeColor={BLUE};fillColor={fill};verticalAlign=top;'
             'align=left;spacingLeft=10;spacingTop=6;fontSize=14;fontFamily=黑体;')
    return cell(value, style, x, y, w, h)


def device(x, y, name_cn, code, model='', ip='', cat=C_NET):
    lines = [f'<b style="font-size:12px">{esc(name_cn)}</b>',
             f'<font face="Consolas" style="font-size:11px" color="#333333">{esc(code)}</font>']
    if model:
        lines.append(f'<font face="Arial" style="font-size:10px" color="#666666">{esc(model)}</font>')
    if ip:
        lines.append(f'<font face="Consolas" style="font-size:10px" color="#2563eb">{esc(ip)}</font>')
    value = '<br>'.join(lines)
    style = (f'rounded=1;whiteSpace=wrap;html=1;fillColor={cat};strokeColor={BLACK};'
             'fontFamily=黑体;verticalAlign=middle;align=center;spacing=4;')
    return cell(value, style, x, y, 170, 62)


def edge(value, style, src, dst):
    return cell(value, style, 0, 0, 0, 0, edge=True, source=src, target=dst)


def text(x, y, w, h, value, style_extra=''):
    style = (f'text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;'
             f'fontFamily=黑体;fontSize=11;{style_extra}')
    return cell(value, style, x, y, w, h)


def main():
    cells = []
    ids = {}

    def add(fn, *args, **kw):
        cid, xml = fn(*args, **kw)
        cells.append(xml)
        return cid

    # ---------- 区域 ----------
    add(region, 40, 40, 1320, 140, '互联网出口区（Internet）', '运营商接入 / 公网IP')
    add(region, 40, 210, 1320, 150, '边界防护层（DMZ）', '路由器 → 防火墙 → IPS/上网行为管理')
    add(region, 40, 390, 1320, 130, '核心交换层（Core）', '核心交换机双机 + 链路聚合')
    add(region, 60, 550, 610, 160, '业务服务器区（App-Server）', '业务网段：10.10.1.0/24')
    add(region, 690, 550, 650, 160, '核心数据区（Data-Core）', '数据网段：10.10.3.0/24')
    add(region, 60, 740, 610, 130, '安全管理区（Security-Mgmt）', '管理网段：10.10.5.0/24')
    add(region, 690, 740, 650, 130, '办公接入区（Office）', '办公网段：10.10.6.0/24')

    # ---------- 设备卡片 ----------
    ids['RT-EDGE'] = add(device, 100, 100, '边界路由器', 'RT-Edge-01', 'Cisco 8200', '公网IP:2.2.2.1', C_NET)
    ids['GM'] = add(device, 330, 100, '光猫', 'ONU-01', '运营商设备', '', C_NET)
    ids['FW-EDGE'] = add(device, 100, 270, '边界防火墙', 'FW-Edge-01', 'Huawei USG6650', '内网IP:10.10.0.1', C_SEC)
    ids['IPS'] = add(device, 330, 270, '入侵防御系统', 'IPS-01', '绿盟 NIPSNX3', 'IP:10.10.0.2', C_SEC)
    ids['WAF'] = add(device, 560, 270, 'Web应用防火墙', 'WAF-01', '绿盟 WAFNX3', 'IP:10.10.0.3', C_SEC)
    ids['UAM'] = add(device, 790, 270, '上网行为管理', 'UAM-01', '迪普 UAG3000', 'IP:10.10.0.4', C_SEC)
    ids['RT-CORE'] = add(device, 100, 425, '核心路由器', 'RT-Core-01', 'H3C SR6608', '管理IP:10.10.0.254', C_NET)
    ids['SW-CORE1'] = add(device, 520, 425, '核心交换机', 'SW-Core-01', 'H3C S7503E-S', '管理IP:10.10.0.2', C_NET)
    ids['SW-CORE2'] = add(device, 760, 425, '核心交换机', 'SW-Core-02', 'H3C S7503E-S', '管理IP:10.10.0.3', C_NET)
    ids['WEB'] = add(device, 110, 600, 'Web应用服务器', 'Service-Web-01', 'Dell PowerEdge R750', 'IP:10.10.1.10:8080', C_SVR)
    ids['APP'] = add(device, 330, 600, '业务应用服务器', 'Service-App-01', 'Dell PowerEdge R750', 'IP:10.10.1.11:8080', C_SVR)
    ids['AUTH'] = add(device, 550, 600, '认证服务器', 'Service-Auth-01', 'Dell PowerEdge R650', 'IP:10.10.1.12:8443', C_SVR)
    ids['MYSQL'] = add(device, 740, 600, 'MySQL数据库', 'DB-MySQL-01', 'MySQL 8.0.35', 'IP:10.10.3.10:3306', C_DB)
    ids['REDIS'] = add(device, 960, 600, 'Redis缓存', 'DB-Redis-01', 'Redis 7.0.12', 'IP:10.10.3.20:6379', C_DB)
    ids['STORE'] = add(device, 1180, 600, '存储设备', 'Store-01', 'Dell PowerStore', '管理IP:10.10.4.10', C_DB)
    ids['BJ'] = add(device, 110, 780, '堡垒机', 'BJ-01', '齐治堡垒机', 'IP:10.10.5.10', C_SEC)
    ids['LOG'] = add(device, 330, 780, '日志审计系统', 'Log-Audit-01', '绿盟 LASNX3', 'IP:10.10.5.20', C_SEC)
    ids['DBA'] = add(device, 550, 780, '数据库审计系统', 'DB-Audit-01', '绿盟 DAS', 'IP:10.10.5.30', C_SEC)
    ids['SW-ACC'] = add(device, 740, 780, '接入交换机', 'SW-Acc-01', 'H3C S5130', 'VLAN 40', C_NET)
    ids['PC1'] = add(device, 960, 780, '用户终端', 'PC-User-01', '联想 ThinkCentre', 'IP:10.10.6.100', C_CLI)
    ids['PC2'] = add(device, 1180, 780, '运维终端', 'PC-Ops-01', '联想 ThinkCentre', 'IP:10.10.6.101', C_CLI)

    # ---------- 连线（规范 §3.4 线型） ----------
    LINK = 'endArrow=blockThin;html=1;fontFamily=黑体;fontSize=10;'
    add(edge, '网线 千兆', f'strokeColor={BLACK};strokeWidth=2;html=1;fontFamily=黑体;fontSize=10;',
        ids['RT-EDGE'], ids['FW-EDGE'])
    add(edge, '光纤 10G', f'strokeColor={ORANGE};strokeWidth=2;html=1;fontFamily=黑体;fontSize=10;',
        ids['FW-EDGE'], ids['SW-CORE1'])
    add(edge, 'LACP x2', f'strokeColor={PURPLE};strokeWidth=2.5;html=1;fontFamily=黑体;fontSize=10;',
        ids['SW-CORE1'], ids['SW-CORE2'])
    add(edge, '', f'strokeColor={PURPLE};strokeWidth=2.5;html=1;',
        ids['SW-CORE1'], ids['SW-CORE2'])
    add(edge, '备用链路', f'strokeColor={LGRAY};strokeWidth=1.5;dashPattern=4 2;html=1;fontFamily=黑体;fontSize=10;',
        ids['RT-CORE'], ids['SW-CORE1'])
    add(edge, '业务流', f'strokeColor={BLUE};strokeWidth=2.5;{LINK}', ids['SW-CORE1'], ids['WEB'])
    add(edge, '业务流', f'strokeColor={BLUE};strokeWidth=2.5;{LINK}', ids['SW-CORE1'], ids['MYSQL'])
    add(edge, '管理 SSH', f'strokeColor={GRAY};strokeWidth=1.5;dashed=1;endArrow=open;html=1;fontFamily=黑体;fontSize=10;',
        ids['SW-CORE1'], ids['BJ'])
    add(edge, '网线 千兆', f'strokeColor={BLACK};strokeWidth=2;html=1;fontFamily=黑体;fontSize=10;',
        ids['SW-CORE2'], ids['SW-ACC'])
    add(edge, '业务流', f'strokeColor={BLUE};strokeWidth=2.5;{LINK}', ids['WEB'], ids['MYSQL'])
    add(edge, '写入/查询', f'strokeColor={BLUE};strokeWidth=2.5;{LINK}', ids['MYSQL'], ids['REDIS'])
    add(edge, '管理 SSH', f'strokeColor={GRAY};strokeWidth=1.5;dashed=1;endArrow=open;html=1;fontFamily=黑体;fontSize=10;',
        ids['BJ'], ids['LOG'])
    add(edge, '网线 千兆', f'strokeColor={BLACK};strokeWidth=2;html=1;fontFamily=黑体;fontSize=10;',
        ids['SW-ACC'], ids['PC1'])
    add(edge, '网线 千兆', f'strokeColor={BLACK};strokeWidth=2;html=1;fontFamily=黑体;fontSize=10;',
        ids['SW-ACC'], ids['PC2'])

    # ---------- 标题栏（§2.4） ----------
    add(text, 1030, 22, 340, 130,
        '<b style="font-size:18px">《XX系统网络拓扑图》</b><br>'
        '<font face="Arial" style="font-size:10px" color="#666666">版本：V1.0　｜　绘制日期：YYYY-MM-DD</font><br>'
        '<font face="Arial" style="font-size:10px" color="#666666">运维责任人：＿＿＿＿／＿＿＿＿</font><br>'
        '<font face="Arial" style="font-size:10px" color="#666666">适用范围：＿＿＿＿＿＿＿＿＿＿</font>')

    # ---------- 图例（§8） ----------
    add(region, 60, 900, 620, 150, '设备图标图例', '', '#FDF6EC')
    add(text, 80, 930, 580, 110,
        '■ <b>网络设备</b>（路由器/交换机/负载均衡）　■ <b>安全设备</b>（防火墙/堡垒机/审计）<br>'
        '■ <b>服务器</b>（Web/应用/认证）　■ <b>数据库/存储</b>（MySQL/Redis/存储）<br>'
        '■ <b>客户端</b>（用户终端/运维终端）<br>'
        '<font color="#999999" style="font-size:10px">设备图标从左侧形状库「丰功信息-网络设备」拖入，'
        '统一使用双行标注：中文名+设备代码</font>')
    add(region, 700, 900, 660, 150, '线缆图例', '', '#F0F7F0')
    add(text, 720, 930, 620, 110,
        '<font color="#0050EF"><b>━━━━▶</b></font> 业务数据流（深蓝粗实线）　'
        '<font color="#333333"><b>━━━━</b></font> 物理网线（黑）<br>'
        '<font color="#FF6600"><b>━━━━</b></font> 光纤互联（橙）　'
        '<font color="#666666"><b>- - -</b></font> 管理维护流（灰虚线）<br>'
        '<font color="#9B59B6"><b>━━━━</b></font> 链路聚合 LACP（紫双线）　'
        '<font color="#CCCCCC"><b>-·-·-</b></font> 备用/未启用（浅灰点划线）<br>'
        '<font color="#999999" style="font-size:10px">所有线路中段标注类型：网线 千兆／光纤 10G／管理 SSH／暂未启用</font>')

    # ---------- 组装 XML ----------
    body = '\n'.join(cells)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="app.diagrams.net" agent="itsm-build-templates" version="24.0.0" type="device">\n'
        '  <diagram id="network-topology-template" name="网络拓扑模板">\n'
        '    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{PAGE_W}" pageHeight="{PAGE_H}" math="0" shadow="0">\n'
        '      <root>\n'
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        f'{body}\n'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n'
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(xml)
    print(f'已生成 {OUT}（{len(cells)} 个元素）')


if __name__ == '__main__':
    main()
