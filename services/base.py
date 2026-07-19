# -*- coding: utf-8 -*-
"""Service 层基础工具"""
from functools import wraps


class ServiceError(Exception):
    """业务层异常：路由层捕获后转 flash"""
    def __init__(self, message, code='danger'):
        super().__init__(message)
        self.message = message
        self.code = code


def transaction(func):
    """装饰器：自动 commit/rollback

    用法：
        @transaction
        def my_op(...):
            # 任意 SQL 操作
    """
    from models import db
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise
    return wrapper
