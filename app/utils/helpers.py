# -*- coding: utf-8 -*-
#  Вспомогательные функции для работы приложения.

import os
import re
from flask import current_app
from typing import Optional, List, Dict, Any, Union

def allowed_file(filename: str) -> bool:
    # Проверяет, имеет ли файл допустимое расширение 
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def sanitize_filename(filename: str) -> str:
    # Очищает имя файла от недопустимых символов 
    # Заменяем небезопасные символы подчеркиванием
    return re.sub(r'[^\w\.-]', '_', filename)

def extract_text_from_html(html_content: str) -> str:
    # Извлекает чистый текст из HTML-контента 
    # Удаляем HTML-теги
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Удаляем лишние пробелы и переносы строк
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_file_extension(filename: str) -> str:
    # Возвращает расширение файла
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def create_relative_path(base_dir: str, file_path: str) -> str:
    # Создает относительный путь от base_dir к file_path 
    return os.path.relpath(file_path, base_dir)

def format_book_title(title: str) -> str:
    # Форматирует название книги для отображения
    # Ограничиваем длину и добавляем многоточие, если нужно
    max_length = 50
    if len(title) > max_length:
        return title[:max_length] + '...'
    return title

def format_author_name(author: str) -> str:
    # Форматирует имя автора для отображения 
    # Если имя содержит запятую, меняем местами части (Фамилия, Имя -> Имя Фамилия)
    if ',' in author:
        parts = [part.strip() for part in author.split(',')]
        return ' '.join(parts[::-1])
    return author

def truncate_text(text: str, max_length: int = 200) -> str:
    # Обрезает текст до указанной длины с добавлением многоточия
    if len(text) <= max_length:
        return text
    # Обрезаем по последнему полному слову
    truncated = text[:max_length].rsplit(' ', 1)[0]
    return truncated + '...'

def count_words(text: str) -> int:
    # Подсчитывает количество слов в тексте 
    return len(re.findall(r'\b\w+\b', text))

def split_into_sentences(text: str) -> List[str]:
    # Разбивает текст на предложения
    return re.split(r'(?<=[.!?])\s+', text)