"""WSGI entry point for Gunicorn production deployment."""
import os
from app import create_app, init_db

os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

app = create_app()
init_db(app)
