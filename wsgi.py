"""WSGI entry point for production servers such as Waitress or Gunicorn."""

from app import create_app

# A production WSGI server imports this object once, for example:
# `waitress-serve --listen=0.0.0.0:5000 wsgi:app`.
app = create_app()
