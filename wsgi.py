"""WSGI entry point for Gunicorn production deployment."""
import os
from app import create_app
from utils.crypto import ensure_master_key_available

os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)
ensure_master_key_available()

app = create_app()
