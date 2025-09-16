# config.py
import os
from decimal import Decimal

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # SECRET_KEY: change en prod, ou set via variable d'env
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # DATABASE: preferer DATABASE_URL (Postgres) sinon fallback SQLite local (dev)
    # Ex: postgresql+psycopg2://user:pass@host:5432/dbname
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:Qvlzar1706%40@localhost:5432/Stimlink_online"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(basedir, "static", "uploads"))
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

    # Pagination / autres valeurs par défaut
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 20))

    # Valeurs monétaires par défaut
    DEFAULT_CURRENCY = "CDF"

    # Debug mode (False en production)
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
