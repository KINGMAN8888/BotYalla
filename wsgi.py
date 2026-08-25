"""نقطة دخول الإنتاج عبر Gunicorn:  gunicorn -c gunicorn_conf.py wsgi:app"""
from app import app, bootstrap
bootstrap()
