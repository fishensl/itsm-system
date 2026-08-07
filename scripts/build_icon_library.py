# -*- coding: utf-8 -*-
"""丰功信息网络设备图标库生成脚本。

从 static/stencils/network-security.drawio.xml（网络安全设备 63 图标）中
按映射抽取常用网络/安全/服务器/存储/客户端图标，配合 scripts/icon_svgs/ 新增
缺口图标（认证服务器/业务应用服务器/MySQL/Redis/存储设备），生成：

    static/stencils/fengong-network.drawio.xml   （丰功信息-网络设备）

幂等：重复运行结果一致。新增图标 SVG 源放 scripts/icon_svgs/*.svg。

用法（项目根目录）：
    python scripts/build_icon_library.py
"""
import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_CLIB = os.path.join(ROOT, 'static', 'stencils', 'network-security.drawio.xml')
OUT_CLIB = os.path.join(ROOT, 'static', 'stencils', 'fengong-network.drawio.xml')
SVG_DIR = os.path.join(ROOT, 'scripts', 'icon_svgs')

# 现有库 title → 规范命名（附录A 风格）映射
TITLE_MAP = {
    '路由器': '路由器', '无线路由器': '无线路由器',
    '核心交换机': '核心交换机', '汇聚交换机': '汇聚交换机', '接入交换机': '接入交换机',
    '防火墙': '防火墙', '虚拟防火墙': '虚拟防火墙',
    '负载均衡': '负载均衡器',
    '上网行为管理': '上网行为管理', 'WAF': 'Web应用防火墙', 'VPN': 'VPN',
    '入侵防御系统': '入侵防御系统(IPS)', '入侵检测': '入侵检测系统(IDS)',
    '态势感知系统': '态势感知系统', '威胁情报系统': '威胁情报系统',
    '堡垒机': '堡垒机', '日志审计系统': '日志审计系统', '日志采集器': '日志采集器',
    '数据库审计系统': '数据库审计系统', '数据库审计': '数据库审计',
    '网闸': '网闸', '光闸': '光闸', '网页防篡改': '网页防篡改',
    '脆弱性扫描': '脆弱性扫描', '渗透测试': '渗透测试', '蜜罐系统': '蜜罐',
    '主机安全系统': '主机安全', '杀毒软件': '杀毒软件', '沙箱': '沙箱',
    '终端准入系统': '终端准入', '终端防泄漏': '终端防泄漏',
    '网络准入系统': '网络准入', '网管平台': '网管平台',
    '服务器': '服务器', '服务器集群': '服务器集群', 'ESXI': 'ESXI主机',
    'Web服务器': 'Web应用服务器', 'FTP服务器': '文件服务器', '邮件服务器': '邮件服务器',
    '软件服务器': '软件服务器', '数据库服务器': '数据库服务器',
    '存储阵列': '存储阵列', '存储服务器': '存储服务器',
    '台式机': '用户终端', '笔记本': '笔记本',
    '光猫': '光猫', 'AP': '无线AP', '摄像头': '摄像头',
    '互联网': '互联网', '密码机': '密码机', '短信网关': '短信网关',
    '安全检测': '安全检测', '资产测绘系统': '资产测绘', '代码审计': '代码审计',
    '配置核查': '配置核查',
}

# 新增缺口图标：SVG 文件名（scripts/icon_svgs/）→ 规范命名
NEW_ICONS = [
    ('mysql-db.svg', 'MySQL数据库'),
    ('redis-db.svg', 'Redis缓存'),
    ('auth-server.svg', '认证服务器'),
    ('app-server.svg', '业务应用服务器'),
    ('storage.svg', '存储设备'),
]


def load_source_entries():
    with open(SRC_CLIB, encoding='utf-8') as f:
        data = f.read()
    m = re.search(r'<mxlibrary[^>]*>(.*)</mxlibrary>', data, re.S)
    return json.loads(m.group(1))


def svg_to_png_datauri(svg_path):
    import cairosvg
    png = cairosvg.svg2png(url=svg_path, output_width=80, output_height=80)
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


def _png_datauri(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _fallback_icon(fname):
    """cairosvg 不可用（如 Windows 无 libcairo）时用 PIL 绘制等价图标"""
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for name in ('simhei.ttf', 'msyh.ttc', 'arial.ttf'):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    img = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    name = os.path.basename(fname)
    if name == 'mysql-db.svg':
        d.ellipse((14, 8, 66, 28), fill='#0050EF')
        d.rectangle((14, 18, 66, 44), fill='#3D7BFF')
        d.ellipse((14, 34, 66, 54), fill='#7FA8FF')
        d.rectangle((14, 44, 66, 46), fill='#7FA8FF')
        d.text((40, 22), 'MySQL', font=_font(15), fill='white', anchor='mm')
        d.text((40, 72), 'DB-MySQL', font=_font(8), fill='#1e3a8a', anchor='mm')
    elif name == 'redis-db.svg':
        d.ellipse((14, 6, 66, 26), fill='#0F766E')
        d.rectangle((14, 16, 66, 42), fill='#14B8A6')
        d.ellipse((14, 32, 66, 52), fill='#5EEAD4')
        d.text((40, 20), 'Redis', font=_font(15), fill='white', anchor='mm')
        d.text((40, 72), 'DB-Redis', font=_font(8), fill='#134E4A', anchor='mm')
    elif name == 'auth-server.svg':
        d.rounded_rectangle((16, 10, 64, 70), radius=6, fill='#2563EB')
        d.rounded_rectangle((16, 10, 64, 23), radius=6, fill='#1D4ED8')
        d.ellipse((28, 14, 32, 18), fill='#93C5FD')
        d.ellipse((36, 14, 40, 18), fill='#93C5FD')
        d.rounded_rectangle((23, 30, 57, 36), radius=3, fill='#93C5FD')
        d.rounded_rectangle((23, 42, 57, 48), radius=3, fill='#93C5FD')
        d.rounded_rectangle((23, 54, 57, 60), radius=3, fill='#93C5FD')
        d.text((40, 76), '认证服务器', font=_font(9), fill='#1e3a8a', anchor='mm')
    elif name == 'app-server.svg':
        d.rounded_rectangle((16, 10, 64, 70), radius=6, fill='#059669')
        d.rounded_rectangle((16, 10, 64, 23), radius=6, fill='#047857')
        d.ellipse((28, 14, 32, 18), fill='#A7F3D0')
        d.ellipse((36, 14, 40, 18), fill='#A7F3D0')
        d.rounded_rectangle((23, 30, 57, 36), radius=3, fill='#A7F3D0')
        d.rounded_rectangle((23, 42, 57, 48), radius=3, fill='#A7F3D0')
        d.pieslice((56, 52, 70, 66), 0, 360, fill='#FCD34D')
        d.ellipse((60, 56, 66, 62), fill='#059669')
        d.text((40, 76), '业务应用服务器', font=_font(9), fill='#064e3b', anchor='mm')
    elif name == 'storage.svg':
        d.rounded_rectangle((18, 14, 62, 36), radius=3, fill='#475569')
        d.rounded_rectangle((21, 18, 59, 23), radius=2, fill='#94A3B8')
        d.rounded_rectangle((21, 26, 47, 31), radius=2, fill='#94A3B8')
        d.ellipse((53, 26.5, 56, 30.5), fill='#E2E8F0')
        d.rounded_rectangle((12, 40, 56, 62), radius=3, fill='#64748B')
        d.rounded_rectangle((15, 44, 53, 49), radius=2, fill='#CBD5E1')
        d.rounded_rectangle((15, 52, 41, 57), radius=2, fill='#CBD5E1')
        d.rounded_rectangle((56, 36, 70, 66), radius=2, fill='#334155')
        d.rounded_rectangle((58.5, 40, 67.5, 44), radius=1, fill='#94A3B8')
        d.rounded_rectangle((58.5, 48, 67.5, 52), radius=1, fill='#94A3B8')
        d.rounded_rectangle((58.5, 56, 67.5, 60), radius=1, fill='#94A3B8')
        d.text((40, 76), '存储设备', font=_font(9), fill='#1e293b', anchor='mm')
    else:
        raise ValueError(f'未实现 PIL 兜底: {name}')
    return _png_datauri(img)


def icon_datauri(svg_path):
    try:
        return svg_to_png_datauri(svg_path)
    except Exception:
        print(f'[提示] cairosvg 不可用，改用 PIL 绘制: {os.path.basename(svg_path)}')
        return _fallback_icon(svg_path)


def main():
    entries = []
    src = load_source_entries()
    used = set()
    for entry in src:
        title = entry.get('title', '')
        new_title = TITLE_MAP.get(title)
        if new_title:
            entries.append({
                'data': entry['data'], 'w': entry.get('w', 80), 'h': entry.get('h', 80),
                'title': new_title,
            })
            used.add(title)
    missing = [t for t in TITLE_MAP if t not in used]
    if missing:
        print('[警告] 源库缺少以下图标（跳过）:', '、'.join(missing))

    for fname, title in NEW_ICONS:
        path = os.path.join(SVG_DIR, fname)
        if not os.path.isfile(path):
            print(f'[警告] 缺失 SVG 源: {fname}，跳过 {title}')
            continue
        entries.append({'data': icon_datauri(path), 'w': 80, 'h': 80, 'title': title})

    # 排序：按标题拼音顺序不稳定，保持映射顺序即可（新增图标在末尾）
    xml = '<mxlibrary title="丰功信息-网络设备">' + json.dumps(
        entries, ensure_ascii=False, separators=(',', ':')) + '</mxlibrary>'
    with open(OUT_CLIB, 'w', encoding='utf-8') as f:
        f.write(xml)
    print(f'已生成 {OUT_CLIB}（{len(entries)} 个图标）')


if __name__ == '__main__':
    main()
