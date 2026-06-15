# -*- coding: utf-8 -*-
"""Service 层：把业务规则从路由层分离

约束：
- 接收 db.session 隐式（通过 `from models import db`），不在签名上传递
- 接收表单数据用 dict/Model 对象，不直接拿 Flask request
- 抛出领域异常（ServiceError），路由层捕获后转 flash
"""
from .base import ServiceError

__all__ = ['ServiceError']
