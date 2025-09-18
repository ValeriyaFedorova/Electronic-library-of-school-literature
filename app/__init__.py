# -*- coding: utf-8 -*-
# Инициализация Flask-приложения "Электронная библиотека школьной литературы".
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.config import Config

# Инициализация расширений
db = SQLAlchemy()

def create_app(test_config=None):
    """Создание и настройка Flask приложения"""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)  # Загружаем настройки из класса Config

    # Загрузка конфигурации
    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    # Создание папок, если они не существуют
    try:
        os.makedirs(app.instance_path, exist_ok=True)   
        os.makedirs(Config.BOOKS_DIR, exist_ok=True)
        os.makedirs(Config.CHARACTERS_DIR, exist_ok=True)
    except OSError:
        pass
    
    # Инициализация БД с приложением
    db.init_app(app)

    # Инициализация Flask-Login
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    from app.models.user import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        # Регистрация моделей
        from app.models import book, user
        
        # Создание таблиц
        db.create_all()
        
        # Автоматическая загрузка существующих книг
        from app.services.initializer import initialize_existing_books
        initialize_existing_books()
        
        # Регистрация представлений (контроллеров)
        from app.controllers import book_controller, auth_controller
        app.register_blueprint(book_controller.bp)
        app.register_blueprint(auth_controller.bp, url_prefix='/auth')
        
        # Установка главного маршрута
        app.add_url_rule('/', endpoint='books.index')
        
        return app