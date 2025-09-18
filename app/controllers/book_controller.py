# -*- coding: utf-8 -*-
# Контроллер для работы с книгами и главами
from flask import (
    Blueprint, render_template, abort, current_app, url_for, redirect, request, jsonify, flash
)
from werkzeug.exceptions import NotFound
from flask_login import login_required, current_user
from pathlib import Path
from app import db
from app.services.book_service import (
    get_books,
    get_book_by_id,
    get_chapter_by_id,
    get_chapters_by_book_id,
    get_characters_by_book_id,
    get_character_by_id,
    highlight_characters,
    get_character_appearances,
    process_chapter_for_characters
)
from app.models.book import Chapter, Character, CharacterAppearance
from flask import send_from_directory
from sqlalchemy import text 
from app.models.user import Bookmark
# Добавьте эти импорты в самый верх файла
from sqlalchemy.exc import OperationalError
import time

def set_connection_charset():
    db.session.execute(text('SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci'))
    db.session.commit()

# Создаем Blueprint
bp = Blueprint('books', __name__, url_prefix='/books')


@bp.route('/', methods=['GET'])
def index():
    """Список всех книг"""
    try:
        set_connection_charset()
        books = get_books()
        return render_template('index.html', books=books)
    except Exception as e:
        current_app.logger.error(f"Error loading books list: {str(e)}")
        abort(500)


@bp.route('/<int:book_id>', methods=['GET'])
def view(book_id: int):
    try:
        set_connection_charset()  # Установка кодировки
        book = get_book_by_id(book_id)
        if not book:
            abort(404)
        
        chapters = get_chapters_by_book_id(book_id)
        return render_template('book.html', book=book, chapters=chapters)
    
    except Exception as e:
        current_app.logger.error(f"Error: {str(e)}")
        abort(500)
                
# Исправленная функция read_chapter
@bp.route('/<int:book_id>/chapter/<int:chapter_id>', methods=['GET'])
def read_chapter(book_id: int, chapter_id: int):
    """Чтение главы книги с подсветкой персонажей и навигацией"""
    try:
        set_connection_charset()
        book = get_book_by_id(book_id)
        chapter = get_chapter_by_id(chapter_id)
        
        # Проверка существования и принадлежности
        if not book or not chapter or chapter.book_id != book_id:
            current_app.logger.warning(f"Chapter {chapter_id} not found in book {book_id}")
            abort(404)

        # Получаем все главы книги для анализа структуры
        all_chapters = Chapter.query.filter_by(book_id=book_id).order_by(Chapter.number).all()
        
        # Строим карту детей: parent_id -> список глав
        children_map = {}
        for chap in all_chapters:
            if chap.parent_id not in children_map:
                children_map[chap.parent_id] = []
            children_map[chap.parent_id].append(chap)
        
        # Сортируем каждую группу по номеру главы
        for parent_id in children_map:
            children_map[parent_id].sort(key=lambda x: x.number)
        
        # Получаем все НЕОБРАБОТАННЫЕ главы до текущей включительно
        unprocessed_chapters = Chapter.query.filter(
            Chapter.book_id == book_id,
            Chapter.number <= chapter.number,
            Chapter.is_processed == False
        ).order_by(Chapter.number).limit(5).all()

        for chap in unprocessed_chapters:
            if not chap.content_path:
                continue
            
            try:
                chap_path = Path(current_app.config['BOOKS_DIR']) / chap.content_path
                
                # Проверка безопасности пути
                if not chap_path.resolve().is_relative_to(Path(current_app.config['BOOKS_DIR'])):
                    current_app.logger.warning(f"Invalid path for chapter {chap.id}")
                    continue

                # Обрабатываем только если глава не была обработана
                with open(chap_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Обрабатываем главу с обработкой ошибок блокировки
                try:
                    process_chapter_for_characters(
                        chapter_id=chap.id,
                        content=content
                    )
                    chap.is_processed = True
                    db.session.commit()
                    current_app.logger.info(f"Processed chapter {chap.number}")
                    
                except OperationalError as e:
                    if "Lock wait timeout" in str(e):
                        db.session.rollback()
                        current_app.logger.warning(f"Lock timeout, retrying chapter {chap.id}")
                        time.sleep(1)
                        
                        # Повторная попытка обработки
                        process_chapter_for_characters(
                            chapter_id=chap.id,
                            content=content
                        )
                        chap.is_processed = True
                        db.session.commit()
                        current_app.logger.info(f"Successfully processed chapter {chap.number} after retry")
                    else:
                        raise
                
            except FileNotFoundError:
                current_app.logger.error(f"File not found: {chap_path}")
            except Exception as e:
                current_app.logger.error(f"Error processing chapter {chap.id}: {str(e)}")
                db.session.rollback()

        # Строим упорядоченный список обходом в глубину (DFS)
        ordered_chapters = []
        
        def build_tree(parent_id):
            """Рекурсивно строит упорядоченный список глав"""
            if parent_id in children_map:
                for child in children_map[parent_id]:
                    ordered_chapters.append(child)
                    build_tree(child.id)  # Рекурсивно добавляем детей
        
        # Начинаем с корневых элементов (parent_id = None)
        build_tree(None)

        # Находим текущую позицию главы в упорядоченном списке
        current_index = next((i for i, ch in enumerate(ordered_chapters) 
                            if ch.id == chapter_id), -1)
        
        # ИСПРАВЛЕНИЕ: Определение навигации с пропуском первой подглавы
        # Определяем следующую главу
        next_chapter = None
        next_index = current_index + 1
        
        # Если это раздел - пропускаем следующую главу (первую подглаву)
        if chapter.parent_id is None:
            # Ищем вторую подглаву или следующий раздел
            skip_count = 0
            while next_index < len(ordered_chapters):
                candidate = ordered_chapters[next_index]
                
                # Если это дочерняя глава текущего раздела
                if candidate.parent_id == chapter.id:
                    skip_count += 1
                    if skip_count >= 2:  # Это вторая подглава
                        next_chapter = candidate
                        break
                else:
                    # Это начало нового раздела
                    next_chapter = candidate
                    break
                
                next_index += 1
        else:
            # Обычная навигация для не-разделов
            if next_index < len(ordered_chapters):
                next_chapter = ordered_chapters[next_index]
        
        # Определяем предыдущую главу
        prev_chapter = None
        prev_index = current_index - 1
        if prev_index >= 0:
            prev_chapter = ordered_chapters[prev_index]
        
        # Получаем родительскую главу для навигации (если есть)
        parent_chapter = Chapter.query.get(chapter.parent_id) if chapter.parent_id else None

        # Инициализация переменных
        chapter_content = "<p>Содержимое недоступно</p>"
        content = ""
        characters = []

        if chapter.content_path:
            try:
                content_path = Path(current_app.config['BOOKS_DIR']) / chapter.content_path
                
                # Проверка безопасности пути
                if not content_path.resolve().is_relative_to(Path(current_app.config['BOOKS_DIR'])):
                    raise PermissionError("Недопустимый путь к файлу")

                # Чтение содержимого файла
                with open(content_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Подсветка персонажей
                characters = get_characters_by_book_id(book_id)
                chapter_content = highlight_characters(content, characters)

            except FileNotFoundError:
                current_app.logger.error(f"File not found: {content_path}")
                chapter_content = "<p>Файл главы не найден</p>"
            except PermissionError as pe:
                current_app.logger.error(f"Security error: {str(pe)}")
                abort(403)
            except Exception as e:
                current_app.logger.error(f"Content processing error: {str(e)}")
                chapter_content = "<p>Ошибка обработки содержимого</p>"
        
        # Проверяем, добавлена ли глава в закладки
        bookmarked = False
        if current_user.is_authenticated:
            bookmark = Bookmark.query.filter_by(
                user_id=current_user.id,
                chapter_id=chapter_id
            ).first()
            bookmarked = bookmark is not None

        return render_template(
            'chapter.html',
            book=book,
            chapter=chapter,
            chapter_content=chapter_content,
            prev_chapter=prev_chapter,
            next_chapter=next_chapter,
            parent_chapter=parent_chapter,
            characters=characters,
            current_chapter_id=chapter_id,
            bookmarked=bookmarked
        )

    except Exception as e:
        current_app.logger.error(f"Critical error in read_chapter: {str(e)}")
        abort(500)

@bp.route('/<int:book_id>/chapter/<int:chapter_id>/bookmark/status', methods=['GET'])
@login_required
def bookmark_status(book_id, chapter_id):
    bookmark = Bookmark.query.filter_by(
        user_id=current_user.id,
        chapter_id=chapter_id
    ).first()
    
    return jsonify({
        'bookmarked': bookmark is not None
    })
        
# Добавим маршрут для обслуживания статических файлов (обложки книг)
@bp.route('/content/<path:filename>')
def serve_content(filename):
    """Обслуживание статических файлов"""
    try:
        books_dir = Path(current_app.config['BOOKS_DIR'])
        return send_from_directory(books_dir, filename)
    except Exception as e:
        current_app.logger.error(f"File serving error: {str(e)}")
        abort(404)

    
@bp.route('/<int:book_id>/character/<int:character_id>/chapters-summary', methods=['GET'])
def character_chapters_summary(book_id, character_id):
    try:
        current_chapter_id = request.args.get('chapter_id', type=int)
        if not current_chapter_id:
            return jsonify({'error': 'Не указана текущая глава'}), 400
            
        character = Character.query.get(character_id)
        if not character or character.book_id != book_id:
            return jsonify({'error': 'Персонаж не найден'}), 404

        # Получаем текущую главу для определения номера
        current_chapter = Chapter.query.get(current_chapter_id)
        if not current_chapter:
            return jsonify({'error': 'Глава не найдена'}), 404

        # Получаем все появления персонажа до текущей главы
        appearances = (
            CharacterAppearance.query
            .join(Chapter)
            .filter(
                CharacterAppearance.character_id == character_id,
                Chapter.book_id == book_id,
                Chapter.number < current_chapter.number
            )
            .order_by(Chapter.number)
            .all()
        )

        # Группируем по главам
        chapters_data = {}
        for app in appearances:
            if app.chapter.id not in chapters_data:
                chapters_data[app.chapter.id] = {
                    'number': app.chapter.number,
                    'title': app.chapter.title,
                    'content': []
                }
            if app.context:
                chapters_data[app.chapter.id]['content'].append(app.context)

        # Форматируем результат
        summaries = []
        for chapter_id, data in chapters_data.items():
            summaries.append({
                'id': chapter_id,
                'number': data['number'],
                'title': data['title'],
                'content': data['content']
            })

        return jsonify({
            'summaries': summaries,
            'character_name': character.name
        })
        
    except Exception as e:
        current_app.logger.error(f"Ошибка: {str(e)}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@bp.after_request
def apply_charset(response):
    """Установка заголовков кодировки для всех ответов"""
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@bp.route('/bookmarks', methods=['GET'])
@login_required
def bookmarks():
    """Просмотр закладок пользователя"""
    user_bookmarks = Bookmark.query.filter_by(user_id=current_user.id)\
                                  .order_by(Bookmark.created_at.desc())\
                                  .all()
    return render_template('bookmarks.html', bookmarks=user_bookmarks)

@bp.route('/<int:book_id>/chapter/<int:chapter_id>/bookmark', methods=['POST'])
@login_required
def toggle_bookmark(book_id, chapter_id):
    """Добавление/удаление закладки"""
    chapter = get_chapter_by_id(chapter_id)
    if not chapter or chapter.book_id != book_id:
        return jsonify({'error': 'Глава не найдена'}), 404
    
    # Проверяем, есть ли уже закладка
    existing = Bookmark.query.filter_by(
        user_id=current_user.id,
        chapter_id=chapter_id
    ).first()
    
    if existing:
        # Удаляем существующую закладку
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'removed'})
    else:
        # Создаем новую закладку
        new_bookmark = Bookmark(
            user_id=current_user.id,
            book_id=book_id,
            chapter_id=chapter_id
        )
        db.session.add(new_bookmark)
        db.session.commit()
        return jsonify({'status': 'added'})

@bp.route('/bookmark/<int:bookmark_id>/delete', methods=['POST'])
@login_required
def delete_bookmark(bookmark_id):
    """Удаление закладки с редиректом на страницу закладок"""
    bookmark = Bookmark.query.get(bookmark_id)
    
    if not bookmark or bookmark.user_id != current_user.id:
        flash('Закладка не найдена', 'danger')
    else:
        db.session.delete(bookmark)
        db.session.commit()
        flash('Закладка успешно удалена', 'success')
    
    return redirect(url_for('books.bookmarks'))