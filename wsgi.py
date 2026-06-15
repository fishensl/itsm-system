"""WSGI entry point for Gunicorn production deployment."""
import os
from app import app, init_db

os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)
init_db()
