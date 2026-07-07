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
        # 用 data 字段（非 xml）——drawio addLibraryEntries 的 data 路径直接创建
        # shape=image;image=data:image/png;base64,... 条目，比 xml 路径可靠
        entries.append({
            'data': 'data:image/png;base64,' + b64,
            'w': 80, 'h': 80,
            'title': name,
            'aspect': 'fixed',
        })
    # JSON 内容必须 XML 转义后才能放进 <mxlibrary>
    from xml.sax.saxutils import escape as xml_escape
    json_str = _json.dumps(entries, ensure_ascii=False)
    xml = '<mxlibrary title="' + xml_escape(title) + '">' + xml_escape(json_str) + '</mxlibrary>'
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return len(entries)


def main():
    if len(sys.argv) < 2:
        print('用法: python scripts/convert-vssx-to-drawio.py <file.vssx> [输出英文名]')
        print('例: python scripts/convert-vssx-to-drawio.py 网络安全设备.vssx network-security')
        sys.exit(1)
    vssx = sys.argv[1]
    # 输出名优先用第二个参数（英文名，避免中文 URL 编码问题），否则用 VSSX 文件名
    base = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(vssx))[0]
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
                icon_bytes = z.read(icon)
                try:
                    # PNG 图标直接用 Pillow 缩放；EMF 用 PowerShell 渲染
                    if icon.lower().endswith('.png'):
                        from PIL import Image as _Img
                        import io as _io
                        img = _Img.open(_io.BytesIO(icon_bytes)).convert('RGBA')
                        canvas = _Img.new('RGBA', (128, 128), (255, 255, 255, 255))
                        ratio = min(128 / img.width, 128 / img.height)
                        nw, nh = int(img.width * ratio), int(img.height * ratio)
                        canvas.paste(img.resize((nw, nh), _Img.LANCZOS),
                                     ((128 - nw) // 2, (128 - nh) // 2), img.resize((nw, nh), _Img.LANCZOS))
                        canvas.convert('RGB').save(png_path, 'PNG')
                    else:
                        render_emf_to_png(icon_bytes, png_path, 128)
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
