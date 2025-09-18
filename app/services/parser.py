# -*- coding: utf-8 -*-
"""
Модуль для парсинга EPUB-файлов с улучшенной обработкой иерархических глав
и правильной настройкой ссылок на первую главу раздела
"""
import os
import re
import ebooklib
from pathlib import Path
import json
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from natasha import MorphVocab, NamesExtractor, Doc, Segmenter, NewsNERTagger, NewsMorphTagger, NewsEmbedding
from bs4 import NavigableString
from urllib.parse import quote
from html import escape

from ebooklib import epub
from bs4 import BeautifulSoup
from flask import current_app

from app import db
from app.config import Config
from app.models.book import Book, Chapter, Character, CharacterAppearance, NameVariant

CHARACTERS_DATA_PATH = Path('data/characters/characters.json')
with open(CHARACTERS_DATA_PATH, 'r', encoding='utf-8') as f:
    CHARACTERS_DATA = json.load(f)

Session = sessionmaker(bind=db.engine)

@contextmanager
def scoped_session():
    """Контекстный менеджер для изолированных сессий с ручным управлением"""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()

def parse_and_save_epub(epub_path: str) -> int:
    """Основная функция парсинга EPUB-файла"""
    filename = Path(epub_path).name
    existing_book = Book.query.filter_by(filename=filename).first()
    if existing_book:
        return existing_book.id

    try:
        with scoped_session() as session:  # Используем локальную сессию
            book = epub.read_epub(epub_path)
            metadata = extract_metadata(book, epub_path)
            
            new_book = Book(
                title=metadata['title'],
                author=metadata['author'],
                filename=filename,
                cover_path=metadata['cover']
            )
            session.add(new_book)
            session.flush()  # Получаем ID без коммита

            # Передаем сессию во все функции
            process_book_structure(session, book, epub_path, new_book.id)
            update_section_links(session, new_book.id)
            extract_characters(session, new_book.id, filename)
            detect_character_appearances(session, new_book.id)

            return new_book.id

    except Exception as e:
        current_app.logger.error(f"Error processing {epub_path}: {str(e)}")
        raise

def extract_metadata(book: epub.EpubBook, epub_path: str) -> Dict:
    """Извлечение метаданных книги"""
    def get_meta_value(metadata: list) -> str:
        return clean_text(metadata[0][0]) if metadata else ""

    return {
        'title': get_meta_value(book.get_metadata('DC', 'title')) or Path(epub_path).stem,
        'author': get_meta_value(book.get_metadata('DC', 'creator')) or "Неизвестен",
        'cover': extract_cover(book)
    }


def extract_cover(book: epub.EpubBook) -> Optional[str]:
    """Извлечение и сохранение обложки"""
    try:
        if cover_meta := book.get_metadata('OPF', 'cover'):
            cover_item = book.get_item_with_id(cover_meta[0][1]['content'])
            if cover_item:
                return save_cover_image(cover_item)
        
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            if 'cover' in item.file_name.lower():
                return save_cover_image(item)
    except Exception as e:
        current_app.logger.warning(f"Ошибка извлечения обложки: {str(e)}")
    return None


def save_cover_image(item) -> str:
    """Сохранение изображения обложки"""
    cover_dir = Config.BOOKS_DIR / 'covers'
    cover_dir.mkdir(exist_ok=True)
    
    ext = Path(item.file_name).suffix or '.jpg'
    cover_path = cover_dir / f"cover_{os.urandom(4).hex()}{ext}"
    cover_path.write_bytes(item.get_content())
    
    # Используем as_posix() для корректных разделителей
    return cover_path.relative_to(Config.BOOKS_DIR).as_posix()


def save_book_metadata(metadata: Dict, filename: str) -> int:
    """Сохранение метаданных книги"""
    book = Book(
        title=metadata['title'],
        author=metadata['author'],
        filename=filename,
        cover_path=metadata['cover']
    )
    db.session.add(book)
    db.session.flush()
    return book.id


def process_book_structure(session, book: epub.EpubBook, epub_path: str, book_id: int) -> None:
    """Обработка структуры книги с учетом специальных случаев"""
    try:
        book_dir = Config.BOOKS_DIR / Path(epub_path).stem
        book_dir.mkdir(exist_ok=True, parents=True)

        # Извлекаем метаданные для определения книги
        metadata = extract_metadata(book, epub_path)
        book_title = metadata['title'].lower()
        
        toc_items = extract_clean_toc(book.toc)
        
        # Применяем специальную обработку
        if "герой нашего времени" in book_title:
            toc_items = process_hero_toc(toc_items)
        elif "мертвые души" in book_title:
            toc_items = process_dead_souls_toc(toc_items)
        elif "евгений онегин" in book_title:
            toc_items = process_onegin_toc(toc_items)
        
        if toc_items:
            process_hierarchical_toc(session, toc_items, book, book_dir, book_id)
        else:
            process_spine_items(session, book, book_dir, book_id)

    except Exception as e:
        current_app.logger.error(f"Ошибка структуры книги: {str(e)}")
        raise

def extract_clean_toc(toc_items, level=0, parent_path="") -> List[Dict]:
    """Рекурсивное извлечение структуры оглавления"""
    result = []
    for i, item in enumerate(toc_items):
        if isinstance(item, tuple):
            link, children = item
            current_path = f"{parent_path}/{i}" if parent_path else str(i)
            # Определяем, является ли элемент разделом
            is_section_item = is_section(link.title) if link.title else False
            result.append({
                'item': link,
                'level': level,
                'path': current_path,
                'is_section': is_section_item
            })
            result.extend(extract_clean_toc(children, level+1, current_path))
        else:
            current_path = f"{parent_path}/{i}" if parent_path else str(i)
            # Определяем, является ли элемент разделом
            is_section_item = is_section(item.title) if item.title else False
            result.append({
                'item': item,
                'level': level,
                'path': current_path,
                'is_section': is_section_item
            })
    result.sort(key=lambda x: [int(p) for p in x['path'].split('/')])        
    return result


def is_section(title: str) -> bool:
    """Определение типа раздела"""
    if not title:
        return False
        
    normalized = re.sub(r'[^\w\s]', '', title, flags=re.IGNORECASE).lower()
    normalized = re.sub(r'[ё]', 'е', normalized)
    
    # Все типы важных разделов, которые должны отображаться в оглавлении
    special_sections = [
        'предисловие', 'действующие лица', 'лица'
    ]
    
    # Если это специальный раздел, он должен быть включен в оглавление
    if any(keyword in normalized for keyword in special_sections):
        return True
    
    patterns = [
        r'^(том|часть|действие|сцена|явление)[\s\-]+',
        r'^[ivxlcdm]+$'
    ]
    return any(re.match(p, normalized) for p in patterns)


def determine_hierarchy_type(toc_items: List[Dict]) -> str:
    """Определение типа иерархии книги на основе оглавления"""
    # Выделяем все типы глав/разделов в оглавлении
    section_types = set()
    for item in toc_items:
        if item['is_section']:
            title = get_chapter_title(item['item']).lower()
            # Проверяем специальные типы
            if 'предисловие' in title:
                section_types.add('preface')
            elif 'действующие лица' in title or 'лица' in title:
                section_types.add('characters')
            elif 'том' in title:
                section_types.add('volume')
            elif 'часть' in title:
                section_types.add('part')
            elif 'действие' in title:
                section_types.add('act')
            elif 'сцена' in title:
                section_types.add('scene')
            elif 'явление' in title:
                section_types.add('appearance')

    # Определение типа иерархии
    if {'volume', 'part'}.issubset(section_types):
        return 'volume_part_chapter'
    elif 'part' in section_types and 'volume' not in section_types:
        return 'part_chapter'
    elif {'act', 'scene', 'appearance'}.issubset(section_types):
        return 'act_scene_appearance'
    elif {'act', 'appearance'}.issubset(section_types) and 'scene' not in section_types:
        return 'act_appearance'
    elif 'characters' in section_types:
        return 'play'
    else:
        return 'default'


def preprocess_toc_items(toc_items: List[Dict]) -> List[Dict]:
    """Предварительная обработка и упорядочивание пунктов оглавления"""
    # Сначала сортируем по пути, чтобы сохранить исходный порядок
    items = sorted(toc_items, key=lambda x: x['path'])
    
    # Выделяем специальные разделы вначале
    special_first = []
    regular_items = []
    
    for item in items:
        title = get_chapter_title(item['item']).lower()
        
        # "Предисловие" и "Действующие лица" должны быть первыми
        if 'предисловие' in title:
            special_first.append(item)
        elif 'действующие лица' in title or 'лица' in title:
            # "Действующие лица" всегда после предисловия, но перед основным содержанием
            if any('предисловие' in get_chapter_title(i['item']).lower() for i in special_first):
                special_first.append(item)
            else:
                special_first.insert(0, item)
        else:
            regular_items.append(item)
    
    # Соединяем списки
    return special_first + regular_items


def process_hierarchical_toc(session, toc_items: List[Dict], book: epub.EpubBook, book_dir: Path, book_id: int) -> None:
    """Обработка вложенных структур с учетом иерархического типа книги"""
    # Определяем тип иерархии
    hierarchy_type = determine_hierarchy_type(toc_items)
    
    # Предобработка: упорядочиваем специальные разделы
    sorted_toc = preprocess_toc_items(toc_items)
    
    # Словарь для отслеживания созданных разделов по уровням
    hierarchy_stack = {}
    
    # Список для отслеживания родительских элементов по уровням
    parent_by_level = {}
    
    for item_data in sorted_toc:
        item = item_data['item']
        title = re.sub(r'^[\s\-]*(\[x?\])?\s*', '', get_chapter_title(item))
        level = item_data['level']
        
        # Определение является ли элемент разделом
        is_section_item = item_data['is_section']
        
        # Определение типа элемента
        element_type = determine_element_type(title, hierarchy_type)
        
        # Находим родителя по логике вложенности
        parent_id = None
        
        # Специальная логика для определения родителя в зависимости от типа иерархии
        if level > 0:
            # Ищем ближайший родитель с уровнем ниже текущего
            for search_level in range(level - 1, -1, -1):
                if search_level in parent_by_level:
                    parent_id = parent_by_level[search_level]
                    break
        
        # Создание главы или раздела
        chapter = create_chapter(
            session=session,  # Передаем сессию в create_chapter
            item=item,
            book=book,
            book_dir=book_dir,
            parent_id=parent_id,
            book_id=book_id,
            level=level,
            is_section=is_section_item,
            element_type=element_type,
            hierarchy_level=level,
            hierarchy_type=hierarchy_type
        )
        
        # Обновление стека для всех элементов, если глава была успешно создана
        if chapter['id']:
            # Запоминаем текущий элемент для данного уровня
            parent_by_level[level] = chapter['id']
            
            # Удаляем все элементы с более высоким уровнем, так как они больше не могут быть родителями
            for key in list(parent_by_level.keys()):
                if key > level:
                    del parent_by_level[key]



def determine_element_type(title: str, hierarchy_type: str) -> str:
    """Определение типа элемента с улучшенным распознаванием"""
    normalized = title.lower()
    
    # Специальные разделы
    if "действующие лица" in normalized or "лица" in normalized:
        return "Действующие лица"
    elif "предисловие" in normalized:
        return "Предисловие"
    elif "вступление" in normalized:
        return "Вступление"
    elif "заключительная" in normalized:
        return "Заключительная глава"
    elif "отрывки" in normalized:
        return "Отрывки"
    
    # Основная иерархия
    if "том" in normalized:
        return "Том"
    elif "часть" in normalized:
        return "Часть"
    elif "действие" in normalized:
        return "Действие"
    elif "сцена" in normalized:
        return "Сцена"
    elif "явление" in normalized:
        return "Явление"
    elif "глава" in normalized:
        return "Глава"
    
    # Дополнительные проверки для римских цифр
    if is_roman_numeral(normalized):
        if hierarchy_type == "play":
            return "Явление"
        return "Глава"
    
    return "Раздел"

def is_roman_numeral(text: str) -> bool:
    """Проверка, является ли текст римской цифрой"""
    return bool(re.match(r'^[IVXLCDM]+$', text.upper()))


def contains_ordinal_number(text: str) -> bool:
    """Проверка, содержит ли текст порядковое числительное"""
    ordinals = ['перв', 'втор', 'трет', 'четверт', 'пят', 'шест', 'седьм', 'восьм', 'девят', 'десят']
    return any(ordinal in text.lower() for ordinal in ordinals)


def roman_to_int(s: str) -> int:
    """Конвертирует римские цифры в целое число"""
    roman_map = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }
    
    # Проверка на валидность римской цифры
    if not all(char in roman_map for char in s.upper()):
        return 0
        
    total = 0
    prev_value = 0
    
    for char in reversed(s.upper()):
        value = roman_map.get(char, 0)
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    return total


def create_chapter(
    session,
    item,
    book: epub.EpubBook,
    book_dir: Path,
    parent_id: Optional[int],
    book_id: int,
    level: int,
    is_section: bool,
    element_type: str,
    hierarchy_level: int,
    hierarchy_type: str
) -> Dict:
    """Создание главы с улучшенной обработкой опечаток"""
    def get_chapter_number(title: str) -> int:
        """Извлекает номер с учетом русских заглавных букв и всех форм"""
        # Проверка на специальные разделы, которые не должны иметь номеров
        normalized_title = re.sub(r'[^\w\s]', '', title.lower())
        special_sections = ['предисловие', 'действующие лица', 'лица']
        for section in special_sections:
            if section in normalized_title:
                return 0  # Возвращаем 0 для специальных разделов
        
        # Нормализация: приводим к нижнему регистру и заменяем ё
        corrected_title = re.sub(r'[ё]', 'е', title.lower())
        
        # Коррекция опечаток с учетом русской раскладки
        corrections = {
            'btорая': 'вторая',
            'bтора': 'вторая',
            'дeйствие': 'действие',  # Латинская 'e' → русская 'е'
            'tom': 'том',
            '4асть': 'часть',
            'тертье': 'третье',  # Исправление опечатки "тертье" → "третье"
        }
        for wrong, correct in corrections.items():
            corrected_title = corrected_title.replace(wrong, correct)

        # Расширенный словарь числительных для всех форм, включая все окончания
        ordinal_map = {
            # Все формы "первый"
            'перв': 1, 'первый': 1, 'первая': 1, 'первое': 1, 'первые': 1, 'первого': 1, 'первому': 1, 'первым': 1, 'первом': 1,
            # Все формы "второй"
            'втор': 2, 'второй': 2, 'вторая': 2, 'второе': 2, 'вторые': 2, 'второго': 2, 'второму': 2, 'вторым': 2, 'втором': 2,
            # Все формы "третий"
            'трет': 3, 'третий': 3, 'третья': 3, 'третье': 3, 'третьи': 3, 'третьего': 3, 'третьему': 3, 'третьим': 3, 'третьем': 3,
            # Все формы "четвертый"
            'четверт': 4, 'четвертый': 4, 'четвертая': 4, 'четвертое': 4, 'четвертые': 4, 'четвертого': 4, 'четвертому': 4, 'четвертым': 4, 'четвертом': 4,
            # Все формы "пятый"
            'пят': 5, 'пятый': 5, 'пятая': 5, 'пятое': 5, 'пятые': 5, 'пятого': 5, 'пятому': 5, 'пятым': 5, 'пятом': 5,
            # Все формы "шестой"
            'шест': 6, 'шестой': 6, 'шестая': 6, 'шестое': 6, 'шестые': 6, 'шестого': 6, 'шестому': 6, 'шестым': 6, 'шестом': 6,
            # Все формы "седьмой"
            'седьм': 7, 'седьмой': 7, 'седьмая': 7, 'седьмое': 7, 'седьмые': 7, 'седьмого': 7, 'седьмому': 7, 'седьмым': 7, 'седьмом': 7,
            'сем': 7,  # Для совместимости со старым кодом
            # Все формы "восьмой"
            'восьм': 8, 'восьмой': 8, 'восьмая': 8, 'восьмое': 8, 'восьмые': 8, 'восьмого': 8, 'восьмому': 8, 'восьмым': 8, 'восьмом': 8,
            # Все формы "девятый"
            'девят': 9, 'девятый': 9, 'девятая': 9, 'девятое': 9, 'девятые': 9, 'девятого': 9, 'девятому': 9, 'девятым': 9, 'девятом': 9,
            # Все формы "десятый"
            'десят': 10, 'десятый': 10, 'десятая': 10, 'десятое': 10, 'десятые': 10, 'десятого': 10, 'десятому': 10, 'десятым': 10, 'десятом': 10,
            # Все формы "одиннадцатый"
            'одиннадцат': 11, 'одиннадцатый': 11, 'одиннадцатая': 11, 'одиннадцатое': 11, 'одиннадцатые': 11, 
            'одиннадцатого': 11, 'одиннадцатому': 11, 'одиннадцатым': 11, 'одиннадцатом': 11,
            # Все формы "двенадцатый"
            'двенадцат': 12, 'двенадцатый': 12, 'двенадцатая': 12, 'двенадцатое': 12, 'двенадцатые': 12, 
            'двенадцатого': 12, 'двенадцатому': 12, 'двенадцатым': 12, 'двенадцатом': 12,
        }

        # Паттерны для поиска номера (регистронезависимые)
        patterns = [
        # Обновленные паттерны для распознавания "Глава N"
        r'(том|часть|действие|сцена|явление|глава)[\s\-]+([а-яё]+)',  
        r'(том|часть|действие|сцена|явление|глава)[\s\-]+([ivxlcdm]+|\d+)',
        r'^([ivxlcdm]+|\d+)$',
        r'(^глава\s+)(\d+)'  # Новый паттерн для явного указания "Глава"
    ]
        
        for pattern in patterns:
            match = re.search(pattern, corrected_title, re.IGNORECASE)
            if match:
                if len(match.groups()) > 1:
                    section_type = match.group(1).lower()
                    number_str = match.group(2).lower()
                    
                    # Обработка римских цифр (XI → 11)
                    if re.fullmatch(r'[ivxlcdm]+', number_str):
                        return roman_to_int(number_str.upper())
                    
                    # Обработка числовых обозначений (1, 2)
                    if number_str.isdigit():
                        return int(number_str)
                    
                    # Проверка полного совпадения с известными числительными
                    if number_str in ordinal_map:
                        return ordinal_map[number_str]
                    
                    # Если полного совпадения нет, ищем начало слова
                    for key in ordinal_map:
                        if number_str.startswith(key):
                            return ordinal_map[key]
                else:
                    # Отдельно стоящие римские цифры
                    number_str = match.group(1).lower()
                    if re.fullmatch(r'[ivxlcdm]+', number_str):
                        return roman_to_int(number_str.upper())
        
        return 0

    href = getattr(item, 'href', None)
    title = get_chapter_title(item)
    content_path = None

    # Проверка существующей главы
    existing = Chapter.query.filter_by(
        book_id=book_id,
        parent_id=parent_id,
        title=title
    ).first()
    
    if existing:
        return {
            'id': existing.id,
            'title': title,
            'content_path': existing.content_path,
            'level': level,
            'is_section': is_section,
            'element_type': element_type,
            'hierarchy_level': hierarchy_level
        }

    # Определение номера и специальной обработки для разделов особого типа
    normalized_title = title.lower()
    if "заключительная" in normalized_title:
        number = 1000  # Большое число для размещения в конце
    elif "отрывки" in normalized_title:
        number = 9  # После главы 8
    elif "вступление" in normalized_title:
        number = 0  # Перед первой главой
    elif 'действующие лица' in normalized_title or 'лица' in normalized_title:
        number = 0  # Специальные разделы не имеют номера
        is_special_section = True
    elif 'предисловие' in normalized_title:
        number = 0  # Предисловие не имеет номера
        is_special_section = True
    else:
        is_special_section = False
        # Извлекаем номер из заголовка для всех элементов
        extracted_number = get_chapter_number(title)
        if extracted_number > 0:
            number = extracted_number
        else:
            # Если не удалось, используем get_next_number
            number = get_next_number(parent_id, is_section)
            if is_section and not is_special_section:
                current_app.logger.warning(f"Не удалось определить номер для раздела: {title}")

    # Обработка контента для не-разделов
    if href:
        content_path = process_content(book.get_item_with_href(href), book_dir, title)

    # Создание объекта главы
    new_chapter = Chapter(
        title=title,
        number=number,
        content_path=content_path,
        parent_id=parent_id,
        is_parent=is_section,
        book_id=book_id,
        element_type=element_type,
        hierarchy_level=hierarchy_level
    )
    
    try:
        session.add(new_chapter)
        session.flush()
        return {
            'id': new_chapter.id,
            'title': title,
            'content_path': content_path,
            'level': level,
            'is_section': is_section,
            'element_type': element_type,
            'hierarchy_level': hierarchy_level
        }
    except Exception as e:
        session.rollback()
        current_app.logger.error(f"Ошибка создания главы: {str(e)}")
        return {'id': None}


def update_section_links(session, book_id: int) -> None:
    """Обновление ссылок разделов"""
    try:
        sections = session.query(Chapter).filter_by(
            book_id=book_id, 
            is_parent=True
        ).all()
        
        for section in sections:
            if not section.content_path:
                first_chapter = session.query(Chapter).filter_by(
                    book_id=book_id,
                    parent_id=section.id
                ).order_by(Chapter.number).first()
                
                if first_chapter and first_chapter.content_path:
                    section.content_path = first_chapter.content_path
        
        session.commit()
    except Exception as e:
        session.rollback()
        raise


def get_next_number(parent_id: Optional[int], is_section: bool) -> int:
    """Получение следующего порядкового номера"""
    if is_section:
        # Для секций ищем в том же родительском разделе
        last = Chapter.query.filter_by(parent_id=parent_id, is_parent=True).order_by(Chapter.number.desc()).first()
    else:
        # Для глав ищем в родительском разделе
        last = Chapter.query.filter_by(parent_id=parent_id).order_by(Chapter.number.desc()).first()
    return last.number + 1 if last else 1


def get_chapter_title(item) -> str:
    """Извлечение заголовка главы"""
    if hasattr(item, 'title') and item.title:
        return clean_text(item.title)
    if hasattr(item, 'href'):
        return Path(item.href).stem.replace('_', ' ').title()
    return "Без названия"


def process_content(doc, book_dir: Path, title: str) -> Optional[str]:
    """Обработка содержимого главы с улучшенной валидацией путей и удалением изображений"""
    try:
        content = doc.get_content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Удаление нежелательных тегов
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'img']):
            tag.decompose()

        # Удаление всех остальных изображений (включая теги picture и source)
        for img in soup.find_all(['img', 'picture', 'source', 'figure']):
            img.decompose()

        # Удаление SVG-графики
        for svg in soup.find_all('svg'):
            svg.decompose()

        # Создание безопасного имени файла
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip() or "untitled"
        filename = f"{safe_title}_{doc.id}.html"
        filepath = book_dir / filename

        # Двойная проверка пути
        if not filepath.resolve().is_relative_to(Config.BOOKS_DIR):
            raise ValueError("Недопустимый путь к файлу главы")

        # Сохранение файла
        filepath.write_text(str(soup), encoding='utf-8')
        current_app.logger.info(f"Сохранена глава: {filepath}")

        # Возвращаем относительный путь как строку с правильными разделителями
        return filepath.relative_to(Config.BOOKS_DIR).as_posix()
    
    except Exception as e:
        current_app.logger.error(f"Ошибка обработки контента: {str(e)}")
        return None


def process_spine_items(session, book: epub.EpubBook, book_dir: Path, book_id: int) -> None:
    """Резервная обработка элементов spine"""
    processed_hrefs = set()
    section_counter = 1
    current_section = None

    for item_id in book.spine:
        item = book.get_item_with_id(item_id)
        if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
            
        href = item.href
        if href in processed_hrefs:
            continue

        title = get_chapter_title(item)
        is_section_item = is_section(title)
        element_type = "Раздел" if is_section_item else "Глава"

        # Создание раздела
        if is_section_item:
            chapter = create_chapter(
                session=session,
                item=item,
                book=book,
                book_dir=book_dir,
                parent_id=None,
                book_id=book_id,
                level=0,
                is_section=True,
                element_type=element_type,
                hierarchy_level=0,
                hierarchy_type="default"
            )
            if chapter['id']:
                current_section = chapter['id']
                section_counter += 1
            continue

        # Создание главы внутри раздела
        if current_section:
            create_chapter(
                item=item,
                book=book,
                book_dir=book_dir,
                parent_id=current_section,
                book_id=book_id,
                level=1,
                is_section=False,
                element_type="Глава",
                hierarchy_level=1,
                hierarchy_type="default"
            )
            processed_hrefs.add(href)


def clean_text(text: str) -> str:
    """Очистка и нормализация текста"""
    return re.sub(r'\s+', ' ', text).strip() if text else ""


def extract_characters(session, book_id: int, filename: str) -> None:
    """Импорт персонажей с корректной обработкой имен"""
    try:
        current_app.logger.debug(f"Поиск персонажей для {filename}")
        book_key = next((k for k in CHARACTERS_DATA.keys() 
                      if filename.lower() in k.lower()), None)
        
        if not book_key:
            current_app.logger.warning(f"Нет данных для {filename}")
            return

        characters = CHARACTERS_DATA[book_key]
        
        for full_name, variants in characters.items():
            # Основное имя уже должно быть без скобок в JSON
            character = Character(
                book_id=book_id,
                name=full_name.strip()
            )
            session.add(character)
            session.flush()
            
            # Добавляем варианты имен
            for variant in variants:
                if variant.strip():
                    session.add(NameVariant(
                        character_id=character.id,
                        variant=variant.strip()
                    ))
        
        session.commit()
    
    except Exception as e:
        session.rollback()
        raise

def detect_character_appearances(session, book_id: int) -> None:
    """Обнаружение упоминаний персонажей без модификации HTML"""
    try:
        # Загрузка персонажей с вариантами имен
        characters = (
            session.query(Character)
            .options(db.joinedload(Character.name_variants))
            .filter(Character.book_id == book_id)
            .all()
        )

        # Создание словаря для поиска
        char_patterns = defaultdict(list)
        for char in characters:
            all_names = [char.name] + [v.variant for v in char.name_variants]
            for name in all_names:
                if name.strip():
                    # Создаем паттерн для поиска целых слов
                    pattern = re.compile(
                        r'\b' + re.escape(name.lower()) + r'\b',
                        flags=re.IGNORECASE | re.UNICODE
                    )
                    char_patterns[char.id].append(pattern)

        # Обработка глав
        chapters = session.query(Chapter).filter(Chapter.book_id == book_id).all()

        for chapter in chapters:
            if not chapter.content_path:
                continue

            content_file = Config.BOOKS_DIR / chapter.content_path
            if not content_file.exists():
                continue

            try:
                # Чтение содержимого как обычного текста
                with open(content_file, 'r', encoding='utf-8') as f:
                    text = f.read().lower()

                # Поиск упоминаний
                found_char_ids = set()
                for char_id, patterns in char_patterns.items():
                    for pattern in patterns:
                        if pattern.search(text):
                            found_char_ids.add(char_id)
                            break  # Не проверяем остальные паттерны для этого персонажа

                # Обновляем записи в БД
                session.query(CharacterAppearance).filter(
                    CharacterAppearance.chapter_id == chapter.id
                ).delete()

                if found_char_ids:
                    session.bulk_save_objects([
                        CharacterAppearance(
                            character_id=char_id,
                            chapter_id=chapter.id
                        ) for char_id in found_char_ids
                    ])

                session.commit()

            except Exception as e:
                session.rollback()
                current_app.logger.error(f"Ошибка в главе {chapter.id}: {str(e)}")
                continue

    except Exception as e:
        session.rollback()
        current_app.logger.error(f"Ошибка обработки персонажей: {str(e)}")
        raise

def custom_toc_processing(book_title: str, toc_items: List[Dict]) -> List[Dict]:
    """Специальная обработка оглавления для книг с нестандартной структурой"""
    normalized_title = book_title.lower()
    
    if "герой нашего времени" in normalized_title:
        return process_hero_toc(toc_items)
    elif "мертвые души" in normalized_title:
        return process_dead_souls_toc(toc_items)
    elif "евгений онегин" in normalized_title:
        return process_onegin_toc(toc_items)
    return toc_items

def flatten_structure(hierarchical_items: List[Dict]) -> List[Dict]:
    """Преобразует иерархическую структуру в плоский список"""
    flat_list = []
    
    def process_items(items, level):
        for item in items:
            # Создаем копию элемента без детей
            new_item = {k: v for k, v in item.items() if k != 'children'}
            new_item['level'] = level
            flat_list.append(new_item)
            
            if 'children' in item:
                process_items(item['children'], level + 1)
    
    process_items(hierarchical_items, 0)
    return flat_list

def process_hero_toc(toc_items: List[Dict]) -> List[Dict]:
    """Исправление структуры для 'Герой нашего времени'"""
    # Создаем правильную иерархию
    hierarchy = []
    
    # Собираем элементы
    book_preface = None
    part1 = None
    part2 = None
    journal = None
    chapters = []
    
    for item in toc_items:
        title = get_chapter_title(item['item']).lower()
        
        if "предисловие" in title and "книге" not in title:
            # Предисловие книги
            book_preface = item
            book_preface['is_section'] = False
            book_preface['element_type'] = "Предисловие"
            book_preface['item'].title = "Предисловие (к книге)"
        elif "часть первая" in title:
            part1 = item
            part1['is_section'] = True
            part1['element_type'] = "Часть"
        elif "часть вторая" in title:
            part2 = item
            part2['is_section'] = True
            part2['element_type'] = "Часть"
        elif "журнал печорина" in title:
            journal = item
            journal['is_section'] = True
            journal['element_type'] = "Раздел"
        else:
            chapters.append(item)
    
    # Формируем структуру
    if book_preface:
        hierarchy.append(book_preface)
    
    if part1:
        part1_children = []
        
        # Добавляем главы первой части
        for chapter in chapters[:]:
            title_lower = get_chapter_title(chapter['item']).lower()
            if "бэла" in title_lower or "максим" in title_lower:
                chapter['is_section'] = False
                chapter['element_type'] = "Глава"
                part1_children.append(chapter)
                chapters.remove(chapter)
        
        # Обрабатываем журнал
        if journal:
            journal_children = []
            
            # Ищем предисловие журнала
            journal_preface = None
            for chapter in chapters[:]:
                title_lower = get_chapter_title(chapter['item']).lower()
                if "предисловие" in title_lower and "журнал" in title_lower:
                    journal_preface = chapter
                    # Модифицируем заголовок для ясности
                    journal_preface['item'].title = "Предисловие (к журналу Печорина)"
                    journal_preface['is_section'] = False
                    journal_preface['element_type'] = "Предисловие"
                    journal_children.append(journal_preface)
                    chapters.remove(journal_preface)
                    break  # Прерываем цикл после нахождения
            
            # Если не нашли по ключевым словам, ищем по контексту
            if not journal_preface:
                # Ищем любой элемент с "предисловие", который еще не обработан
                for chapter in chapters[:]:
                    title_lower = get_chapter_title(chapter['item']).lower()
                    if "предисловие" in title_lower:
                        journal_preface = chapter
                        journal_preface['item'].title = "Предисловие (к журналу Печорина)"
                        journal_preface['is_section'] = False
                        journal_preface['element_type'] = "Предисловие"
                        journal_children.append(journal_preface)
                        chapters.remove(journal_preface)
                        break
            
            # Добавляем главы журнала
            for chapter in chapters[:]:
                title_lower = get_chapter_title(chapter['item']).lower()
                if "тамань" in title_lower:
                    chapter['is_section'] = False
                    chapter['element_type'] = "Глава"
                    journal_children.append(chapter)
                    chapters.remove(chapter)
            
            journal['children'] = journal_children
            part1_children.append(journal)
        
        part1['children'] = part1_children
        hierarchy.append(part1)
    
    if part2:
        part2_children = []
        
        for chapter in chapters:
            title_lower = get_chapter_title(chapter['item']).lower()
            if "княжна" in title_lower or "фаталист" in title_lower:
                chapter['is_section'] = False
                chapter['element_type'] = "Глава"
                part2_children.append(chapter)
        
        part2['children'] = part2_children
        hierarchy.append(part2)
    
    return flatten_structure(hierarchy)

def get_next_chapter(current_chapter_id):
    current_chapter = Chapter.query.get(current_chapter_id)
    if not current_chapter:
        return None

    # Получаем все главы книги в правильном порядке
    book_chapters = Chapter.query.filter_by(book_id=current_chapter.book_id)\
                                .order_by(Chapter.path)\
                                .all()

    # Находим текущую позицию
    current_index = next((i for i, ch in enumerate(book_chapters) 
                         if ch.id == current_chapter_id), -1)
    
    if current_index == -1 or current_index + 1 >= len(book_chapters):
        return None

    # Ищем следующую главу с контентом
    next_index = current_index + 1
    while next_index < len(book_chapters):
        next_chapter = book_chapters[next_index]
        
        # Если это раздел без контента, но с дочерними главами
        if next_chapter.is_parent and not next_chapter.content_path:
            # Получаем первую дочернюю главу раздела
            first_child = Chapter.query.filter_by(parent_id=next_chapter.id)\
                                      .order_by(Chapter.path)\
                                      .first()
            if first_child and first_child.content_path:
                return first_child
        elif next_chapter.content_path:
            return next_chapter
        
        next_index += 1
    
    return None

def process_dead_souls_toc(toc_items: List[Dict]) -> List[Dict]:
    """Исправление структуры для 'Мертвые души'"""
    # Находим заключительную главу
    final_chapter = None
    volume2_start = None
    
    for i, item in enumerate(toc_items):
        title = get_chapter_title(item['item']).lower()
        
        if "том второй" in title:
            volume2_start = i
        elif "заключительная" in title:
            final_chapter = toc_items.pop(i)
            break
    
    # Перемещаем заключительную главу в конец второго тома
    if final_chapter and volume2_start is not None:
        # Ищем конец второго тома
        insert_index = volume2_start + 1
        while insert_index < len(toc_items) and toc_items[insert_index]['level'] > 0:
            insert_index += 1
        toc_items.insert(insert_index, final_chapter)
    
    return toc_items

def process_onegin_toc(toc_items: List[Dict]) -> List[Dict]:
    """Исправление структуры для 'Евгений Онегин'"""
    # Находим специальные элементы
    intro_item = None
    travel_item = None
    
    for i, item in enumerate(toc_items):
        title = get_chapter_title(item['item']).lower()
        
        if "вступление" in title:
            intro_item = item
            item['is_section'] = False  # Вступление - глава
            item['element_type'] = "Вступление"  # Устанавливаем правильный тип
        elif "отрывки из путешествия онегина" in title:
            travel_item = item
            item['element_type'] = "Отрывки"  # Устанавливаем правильный тип

    # Перемещаем вступление в самое начало
    if intro_item:
        toc_items.remove(intro_item)
        toc_items.insert(0, intro_item)  # В самое начало
    
    # Перемещаем отрывки в конец (после главы VIII)
    if travel_item:
        toc_items.remove(travel_item)
        
        # Ищем последнюю главу
        last_chapter_index = -1
        for i, item in enumerate(toc_items):
            if "глава" in get_chapter_title(item['item']).lower():
                last_chapter_index = i
        
        if last_chapter_index >= 0:
            toc_items.insert(last_chapter_index + 1, travel_item)
        else:
            toc_items.append(travel_item)  # Добавляем в конец, если не нашли главы
    
    return toc_items