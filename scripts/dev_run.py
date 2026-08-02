# -*- coding: utf-8 -*-
"""本地开发启动（无 debug reloader，避免 CSRF/模块重载干扰）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('ITSM_SECRET_KEY', 'dev-secret-key-2026')

from app import create_app, init_db

app = create_app()
init_db(app)
app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
