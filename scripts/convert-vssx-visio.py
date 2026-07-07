#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用 Visio COM 自动化导出 VSSX 所有 master 为高质量 PNG（需安装 Visio）

用法: python scripts/convert-vssx-visio.py 网络安全设备.vssx network-security
输出: static/stencils/<name>/<master名>.png + <name>.drawio.xml
"""
import sys, os, re, json, base64
from xml.sax.saxutils import escape as xml_escape


def export_masters_via_visio(vssx_path, out_dir, size=256):
    """用 Visio COM 打开 VSSX，导出每个 master 为 PNG"""
    import win32com.client
    import pythoncom

    abs_vssx = os.path.abspath(vssx_path)
    os.makedirs(out_dir, exist_ok=True)

    # 复制到临时 vsdx（Visio 导出要求可写文件，VSSX 只读打开会报错）
    import shutil, tempfile, time
    tmp_vssx = os.path.join(tempfile.gettempdir(), f'itsm_stencil_{int(time.time())}.vssx')
    shutil.copy(abs_vssx, tmp_vssx)

    pythoncom.CoInitialize()
    visio = win32com.client.DispatchEx('Visio.Application')  # DispatchEx 强制新实例
    visio.AlertResponse = 6  # 自动应答 Yes（Visio 导出时弹 Yes/No 框，6=Yes；不在 try 里，失败直接报）
    print(f'AlertResponse = {visio.AlertResponse}')

    results = []
    try:
        # visOpenCopy=128：打开副本（可写）
        doc = visio.Documents.OpenEx(tmp_vssx, 128)
        print(f'打开 VSSX: {doc.Name}, {doc.Masters.Count} 个 master')

        # 创建新绘图页，Drop master 后清空文字再导出（Master.Export 会把文字标签烤进 PNG）
        new_doc = visio.Documents.Add('')
        page = new_doc.Pages(1)

        for i in range(1, doc.Masters.Count + 1):
            master = doc.Masters(i)
            name = master.Name
            safe = re.sub(r'[^\w一-鿿-]', '_', name)[:30] or 'shape'
            png_file = safe + '.png'
            png_path = os.path.join(out_dir, png_file)
            try:
                # Drop master 到页面
                shape = page.Drop(master, 5, 5)
                # 清空 shape 及所有子 shape 的文字（避免文字烤进图标）
                try:
                    shape.Text = ''
                    for j in range(1, shape.Shapes.Count + 1):
                        shape.Shapes(j).Text = ''
                except Exception:
                    pass
                # 导出到 ASCII 临时路径再移动
                tmp_png = os.path.join(tempfile.gettempdir(), f'v_{i}_{int(time.time())}.png')
                shape.Export(tmp_png)
                shutil.move(tmp_png, png_path)
                shape.Delete()
                sz = os.path.getsize(png_path)
                print(f'  [ok] {name} -> {png_file} ({sz} bytes)')
                results.append((name, png_file))
            except Exception as e:
                print(f'  [fail] {name}: {str(e)[:80]}')

        new_doc.Close()
        doc.Close()
    finally:
        visio.Quit()
        pythoncom.CoUninitialize()

    # Pillow 统一缩放到 size x size 白底
    from PIL import Image as _Img
    for name, png_file in results:
        path = os.path.join(out_dir, png_file)
        img = _Img.open(path).convert('RGBA')
        canvas = _Img.new('RGBA', (size, size), (255, 255, 255, 255))
        ratio = min(size / img.width, size / img.height)
        nw, nh = int(img.width * ratio), int(img.height * ratio)
        resized = img.resize((nw, nh), _Img.LANCZOS)
        canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
        canvas.convert('RGB').save(path, 'PNG')

    return results


def make_drawio_library(shapes, xml_path, png_dir, title):
    entries = []
    for name, png_file in shapes:
        with open(os.path.join(png_dir, png_file), 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        entries.append({
            'data': 'data:image/png;base64,' + b64,
            'w': 80, 'h': 80, 'title': name, 'aspect': 'fixed',
        })
    json_str = json.dumps(entries, ensure_ascii=False)
    xml = '<mxlibrary title="' + xml_escape(title) + '">' + xml_escape(json_str) + '</mxlibrary>'
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return len(entries)


def main():
    if len(sys.argv) < 2:
        print('用法: python scripts/convert-vssx-visio.py <file.vssx> [输出英文名]')
        sys.exit(1)
    vssx = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(vssx))[0]
    out_dir = os.path.join('static', 'stencils', base)

    shapes = export_masters_via_visio(vssx, out_dir, 256)
    print(f'\n导出 {len(shapes)} 个 master')

    xml_path = os.path.join('static', 'stencils', base + '.drawio.xml')
    n = make_drawio_library(shapes, xml_path, out_dir, '网络安全设备')
    print(f'生成 drawio 库: {xml_path} ({n} 个图标)')


if __name__ == '__main__':
    main()
