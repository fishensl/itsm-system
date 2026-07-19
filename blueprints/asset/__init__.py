# -*- coding: utf-8 -*-
"""资产管理蓝图包：设备 CRUD / 字典配置 / 固件版本库 / 配置备份

单蓝图 asset_bp 拆模块组织，端点名保持 asset.* 不变（模板 url_for 零改动）。
"""
from flask import Blueprint

asset_bp = Blueprint('asset', __name__)

# 子模块路由注册（import 即生效，顺序无关）
from blueprints.asset import devices, dicts, firmwares, config_backups  # noqa: F401,E402
