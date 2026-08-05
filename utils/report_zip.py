# -*- coding: utf-8 -*-
"""记录+报告打包下载（巡检/工单报告包 zip）

把汇总 Excel 与筛选范围内各记录的报告文件（工程师上传的现场报告 +
审核通过自动生成的正式 Word）打包为一个 zip，便于一次性归档交付。
"""
import os
import tempfile
import zipfile


def build_records_zip(excel_path, files, zip_name='报告包'):
    """打包 Excel + 报告文件为 zip。

    :param excel_path: 汇总 Excel 完整路径（可为 None）
    :param files: [(完整路径, zip内相对路径), ...] — 仅打包存在的文件，路径防穿越
    :param zip_name: 临时文件名前缀
    :return: zip 完整路径（调用方 send_file 后自行清理）
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip',
                                      prefix=zip_name + '_')
    tmp.close()
    with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
        if excel_path and os.path.isfile(excel_path):
            zf.write(excel_path, '记录明细.xlsx')
        for full, arc in files:
            full = os.path.realpath(full)
            if not os.path.isfile(full):
                continue
            # 防路径穿越：arc 只能有文件名或受控子目录
            arc = arc.replace('\\', '/')
            parts = [p for p in arc.split('/') if p and p not in ('.', '..')]
            if not parts:
                continue
            zf.write(full, '/'.join(parts))
    return tmp.name
