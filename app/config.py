import os
from pathlib import Path

class Config:
    # Основные настройки
    SECRET_KEY = os.getenv('FLASK_SECRET', 'dev_secret_123')
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:1234@127.0.0.1:3306/library?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 299,
        'pool_pre_ping': True
    }
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'epub'}

    # Пути
    BASE_DIR = Path(__file__).parent.parent
    BOOKS_DIR = BASE_DIR / 'data' / 'books'
    CHARACTERS_DIR = BASE_DIR / 'data' / 'characters'
    CACHE_DIR = BASE_DIR / 'cache'

    @classmethod
    def create_dirs(cls):
        """Создает необходимые директории"""
        cls.BOOKS_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)

Config.create_dirs()