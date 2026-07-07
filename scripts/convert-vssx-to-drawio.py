#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VSSX → drawio 图标库转换脚本（Windows，需 .NET System.Drawing）

用法: python scripts/convert-vssx-to-drawio.py 网络安全设备.vssx
输出:
  static/stencils/<basename>/            PNG 图标
  static/stencils/<basename>.drawio.xml  drawio 自定义库 XML

在编辑器中通过 clibs=U:<xml 的 URL> 加载。
"""
import sys, os, zipfile, re, json, subprocess, tempfile, base64

def parse_masters(vssx_path):
    """解析 VSSX，返回 [(name, master_file, icon_path), ...]"""
    with zipfile.ZipFile(vssx_path) as z:
        mx = z.read('visio/masters/masters.xml').decode('utf-8')
        mrels = z.read('visio/masters/_rels/masters.xml.rels').decode('utf-8')

        # Master ID/NameU/rId
        masters = re.findall(
            r"<Master\s+ID='(\d+)'\s+NameU='([^']+)'.*?r:id='([^']+)'", mx, re.DOTALL)
        # rId -> master{N}.xml
        rid_to_file = dict(re.findall(
            r'Id="(\w+)"\s+Type="[^"]+"\s+Target="([^"]+)"', mrels))

        result = []
        for mid, name, rid in masters:
            mfile = rid_to_file.get(rid)
            if not mfile:
                continue
            mfile = 'visio/masters/' + mfile
            # master{N}.xml.rels -> icon
            rels_path = mfile.replace('visio/masters/', 'visio/masters/_rels/') + '.rels'
            icon = None
            if rels_path in z.namelist():
                rc = z.read(rels_path).decode('utf-8')
                m = re.search(r'Target="\.\./media/([^"]+)"', rc)
                if m:
                    icon = 'visio/media/' + m.group(1)
            result.append((name, mfile, icon))
        return result


def render_emf_to_png(emf_bytes, png_path, size=128):
    """用 PowerShell + .NET System.Drawing 将 EMF 渲染为 PNG"""
    tmp_emf = png_path + '.emf'
    with open(tmp_emf, 'wb') as f:
        f.write(emf_bytes)
    ps = (
        'Add-Type -AssemblyName System.Drawing;'
        '$emf = New-Object System.Drawing.Imaging.Metafile("%s");'
        '$bmp = New-Object System.Drawing.Bitmap(%d, %d);'
        '$gfx = [System.Drawing.Graphics]::FromImage($bmp);'
        '$gfx.Clear([System.Drawing.Color]::White);'
        '$gfx.SmoothingMode = "AntiAlias";'
        '$gfx.InterpolationMode = "HighQualityBicubic";'
        '$gfx.DrawImage($emf, 0, 0, %d, %d);'
        '$bmp.Save("%s", [System.Drawing.Imaging.ImageFormat]::Png);'
        '$gfx.Dispose(); $bmp.Dispose(); $emf.Dispose();'
        'Write-Output "OK"'
    ) % (tmp_emf.replace('/', '\\'), size, size, size, size,
         png_path.replace('/', '\\'))
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, timeout=30)
    os.remove(tmp_emf)
    if not os.path.exists(png_path):
        raise RuntimeError('EMF 渲染失败: ' + r.stderr[:200])
    return os.path.getsize(png_path)


def make_drawio_library(shapes, xml_path, png_dir, title):
    """生成 drawio <mxlibrary> XML（PNG 以 base64 嵌入，自包含）

    shapes: [(name, png_filename), ...]
    png_dir: PNG 文件所在目录
    title: 库标题（drawio 侧栏显示名）
    """
    import json as _json
    entries = []
    for name, png_file in shapes:
        png_path = os.path.join(png_dir, png_file)
        with open(png_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        cell_xml = (
            '<mxGraphModel><root><mxCell id="2" value="" '
            'style="shape=image;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;'
            'verticalAlign=top;aspect=fixed;imageAspect=0;image=data:image/png;base64,{b64};" '
            'vertex="1" parent="1"><mxGeometry width="80" height="80" as="geometry"/></mxCell>'
            '</root></mxGraphModel>'
        ).format(b64=b64)
        entries.append({'xml': cell_xml, 'w': 80, 'h': 80, 'title': name})
    xml = '<mxlibrary title="' + title + '">' + _json.dumps(entries, ensure_ascii=False) + '</mxlibrary>'
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return len(entries)


def main():
    if len(sys.argv) < 2:
        print('用法: python scripts/convert-vssx-to-drawio.py <file.vssx>')
        sys.exit(1)
    vssx = sys.argv[1]
    base = os.path.splitext(os.path.basename(vssx))[0]
    out_dir = os.path.join('static', 'stencils', base)
    os.makedirs(out_dir, exist_ok=True)

    masters = parse_masters(vssx)
    print(f'解析到 {len(masters)} 个 master')

    with zipfile.ZipFile(vssx) as z:
        shapes = []
        seen_icons = {}  # 同一图标复用
        for name, mfile, icon in masters:
            if not icon:
                print(f'  [skip] {name}: 无图标')
                continue
            # 文件名安全化
            safe = re.sub(r'[^\w一-鿿-]', '_', name)[:30] or 'shape'
            png_file = safe + '.png'
            png_path = os.path.join(out_dir, png_file)

            if icon in seen_icons:
                # 复用已渲染的图标
                src_png = seen_icons[icon]
                # 仍生成独立文件（不同名称）
                if not os.path.exists(png_path):
                    import shutil
                    shutil.copy(os.path.join(out_dir, src_png), png_path)
            else:
                emf_bytes = z.read(icon)
                try:
                    render_emf_to_png(emf_bytes, png_path, 128)
                    print(f'  [ok] {name} -> {png_file} ({os.path.getsize(png_path)} bytes)')
                except Exception as e:
                    print(f'  [fail] {name}: {e}')
                    continue
                seen_icons[icon] = png_file
            shapes.append((name, png_file))

    xml_path = os.path.join('static', 'stencils', base + '.drawio.xml')
    n = make_drawio_library(shapes, xml_path, png_dir=out_dir, title=base)
    print(f'\n生成 drawio 库: {xml_path} ({n} 个图标)')
    print(f'PNG 目录: {out_dir}/')
    print(f'\n在编辑器中加载: clibs=U:{os.path.basename(xml_path)}')


if __name__ == '__main__':
    main()
