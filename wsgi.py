"""Gunicorn entry point: gunicorn wsgi:app"""

from chat import create_app

app = create_app()
