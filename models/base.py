# -*- coding: utf-8 -*-
"""SQLAlchemy 单例（所有模型模块共享）"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
