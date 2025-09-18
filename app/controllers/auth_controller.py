# app/controllers/auth_controller.py
# -*- coding: utf-8 -*-
# Контроллер аутентификации
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.user import User, Bookmark

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('books.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=remember)
        return redirect(url_for('books.index'))
    
    return render_template('auth/login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('books.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('auth.register'))
        
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Пользователь с таким именем или email уже существует', 'danger')
            return redirect(url_for('auth.register'))
        
        new_user = User(
            username=username,
            email=email
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Регистрация прошла успешно! Теперь вы можете войти', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('books.index'))

@bp.route('/profile', methods=['GET'])
@login_required
def profile():
    """Страница профиля пользователя"""
    return render_template('auth/profile.html')

@bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Удаление аккаунта пользователя с подтверждением пароля"""
    password = request.form.get('password')
    
    if not password:
        flash('Введите пароль для подтверждения', 'danger')
        return redirect(url_for('auth.profile'))
    
    # Проверяем пароль
    if not check_password_hash(current_user.password_hash, password):
        flash('Неверный пароль', 'danger')
        return redirect(url_for('auth.profile'))
    
    try:
        # Удаляем все закладки пользователя
        Bookmark.query.filter_by(user_id=current_user.id).delete()
        
        # Удаляем самого пользователя
        db.session.delete(current_user)
        db.session.commit()
        
        logout_user()
        flash('Ваш аккаунт был успешно удалён', 'success')
        return redirect(url_for('books.index'))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting account: {str(e)}")
        flash('Произошла ошибка при удалении аккаунта', 'danger')
        return redirect(url_for('auth.profile'))
