# -*- coding: utf-8 -*-
# Сервис для работы с книгами, главами и персонажами.
import os
import json
from flask import current_app
from app import db
from app.models.book import Book, Chapter, Character, CharacterAppearance
from typing import List, Dict, Any, Optional, Union
import re
from bs4 import BeautifulSoup
from pathlib import Path


def get_books() -> List[Book]:
    #Получает список всех книг из базы данных
    return Book.query.order_by(Book.title).all()

def get_book_by_id(book_id: int) -> Optional[Book]:
    #Получает книгу по ID
    return Book.query.get(book_id)

def get_chapter_by_id(chapter_id: int) -> Optional[Chapter]:
    #Получает главу по ID
    return Chapter.query.get(chapter_id)

def get_character_by_id(character_id: int) -> Optional[Character]:
    #Получает персонажа по ID
    return Character.query.get(character_id)

def get_chapters_by_book_id(book_id: int) -> List[Chapter]:
    """Get all chapters for a book with hierarchical structure"""
    chapters = Chapter.query.filter_by(book_id=book_id).order_by(Chapter.number).all()
    
    # First, group chapters by parent_id
    children_map = {}
    for chapter in chapters:
        parent_id = chapter.parent_id or 'root'
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(chapter)
    
    # Sort children by number within each parent
    for parent_id, children in children_map.items():
        children_map[parent_id] = sorted(children, key=lambda x: x.number or 0)
    
    # Return only root chapters, sorted by number
    root_chapters = sorted(children_map.get('root', []), key=lambda x: x.number or 0)
    
    return root_chapters


def get_characters_by_book_id(book_id: int) -> List[Character]:
    #Получает всех персонажей книги
    return Character.query.filter_by(book_id=book_id).order_by(Character.name).all()

def get_character_appearances(character_id: int, chapter_id: Optional[int] = None) -> List[CharacterAppearance]:
    query = CharacterAppearance.query.join(
        Chapter, CharacterAppearance.chapter_id == Chapter.id
    ).filter(
        CharacterAppearance.character_id == character_id
    ).filter(
        CharacterAppearance.context != None  # Исключаем пустые записи
    )
    
    if chapter_id:
        target_chapter = get_chapter_by_id(chapter_id)
        if target_chapter:
            query = query.filter(Chapter.number <= target_chapter.number)
    
    return query.order_by(Chapter.number).all()


def save_character(book_id: int, name: str, description: Optional[str] = None, importance: Optional[str] = None) -> int:
    # Сохраняет нового персонажа в базу данных
    # Возвращает ID созданного персонажа
    character = Character(
        book_id=book_id,
        name=name,
        description=description,
        importance=importance
    )
    db.session.add(character)
    db.session.commit()
    return character.id


def find_simple_mention(content: str, character: Character) -> List[Dict[str, Any]]:
    """Находит все упоминания персонажа в тексте с расширенным контекстом для диалогов"""
    try:
        # Генерируем паттерны как в highlight_characters
        patterns = []
        name_variants = get_character_name_variants(character)
        
        for name in name_variants:
            clean_name = re.sub(r'[\'"«»]', '', name).strip()
            if not clean_name:
                continue

            pattern = generate_name_pattern(clean_name)
            patterns.append((re.compile(pattern, re.IGNORECASE), clean_name))

        patterns.sort(key=lambda x: len(x[1]), reverse=True)

        # Парсим HTML с сохранением структуры диалогов
        soup = BeautifulSoup(content, 'html.parser')
        
        # Собираем все текстовые элементы с их позициями
        text_elements = []
        pos = 0
        for element in soup.find_all(text=True):
            if element.parent.name in ['script', 'style']:
                continue
                
            text = str(element)
            text_elements.append({
                'text': text,
                'start': pos,
                'end': pos + len(text),
                'element': element
            })
            pos += len(text) + 1

        # Ищем совпадения и собираем контекст
        mentions = []
        seen_positions = set()

        # Создаем полный текст для поиска
        full_text = ' '.join([te['text'] for te in text_elements])
        
        # Проводим поиск по всему тексту
        for pattern, original_name in patterns:
            for match in pattern.finditer(full_text):
                start, end = match.span()
                
                # Проверяем перекрытие
                if any(s <= start < e or s < end <= e for s, e in seen_positions):
                    continue
                
                # Определяем, в каком текстовом элементе находится совпадение
                current_element = None
                for elem in text_elements:
                    if elem['start'] <= start < elem['end']:
                        current_element = elem
                        break
                
                if not current_element:
                    continue
                    
                elem_idx = text_elements.index(current_element)
                
                # Собираем расширенный контекст
                context_parts = []
                
                # Определяем границы контекста
                start_idx = max(0, elem_idx - 3)
                end_idx = min(len(text_elements) - 1, elem_idx + 3)
                
                # Расширяем границы для диалогов
                if any(te['text'].startswith(('–', '-')) for te in text_elements[start_idx:end_idx+1]):
                    # Находим начало диалога
                    dialog_start = start_idx
                    for i in range(elem_idx, max(0, elem_idx-10), -1):
                        if i < len(text_elements) and text_elements[i]['text'].startswith(('–', '-')):
                            dialog_start = i
                        elif i < elem_idx - 1:
                            break
                    
                    # Находим конец диалога
                    dialog_end = end_idx
                    for i in range(elem_idx, min(len(text_elements), elem_idx+10)):
                        if i < len(text_elements) and text_elements[i]['text'].startswith(('–', '-')):
                            dialog_end = i
                        elif i > elem_idx + 1:
                            break
                    
                    # Обновляем границы с запасом
                    start_idx = max(0, dialog_start - 2)  # 2 элемента перед диалогом
                    end_idx = min(len(text_elements)-1, dialog_end + 2)  # 2 элемента после диалога
                
                # Формируем контекст, пропуская дубликаты
                last_text = None
                for i in range(start_idx, end_idx + 1):
                    text = text_elements[i]['text'].strip()
                    
                    # Пропускаем пустые элементы
                    if not text:
                        continue
                        
                    # Пропускаем повторяющиеся фрагменты
                    if text != last_text:
                        context_parts.append(text)
                        last_text = text
                
                context = ' '.join(context_parts).strip()
                
                # Улучшаем форматирование диалогов
                context = re.sub(r'\s*–\s*', ' – ', context)
                context = re.sub(r'\s*,\s*–', ', –', context)
                
                # Удаляем повторы в контексте
                context = re.sub(r'(.+?)(\1)+', r'\1', context)
                
                mentions.append({
                    'text': match.group(),
                    'original_name': original_name,
                    'context': context,
                    'start': start,
                    'end': end
                })

                seen_positions.add((start, end))

        # Фильтруем дубликаты
        unique_mentions = []
        seen_texts = set()
        for m in mentions:
            # Нормализуем контекст для сравнения
            normalized_context = re.sub(r'\s+', ' ', m['context']).strip()[:100]  # Берем первые 100 символов для сравнения
            
            key = (normalized_context, m['original_name'])
            if key not in seen_texts:
                unique_mentions.append(m)
                seen_texts.add(key)

        return unique_mentions

    except Exception as e:
        current_app.logger.error(f"Error in find_simple_mention: {str(e)}")
        return []
    
def generate_name_pattern(name: str) -> str:
    """Генерирует regex-паттерн для имени с учетом русской морфологии"""
    if ' ' in name:
        # Обработка составных имен
        parts = name.split()
        return r'\b' + r'\s+'.join([generate_single_name_pattern(p) for p in parts]) + r'\b'
    return r'\b' + generate_single_name_pattern(name) + r'\b'


def generate_single_name_pattern(name: str) -> str:
    """Генерирует паттерн для одного имени"""
    if len(name) < 3:
        return re.escape(name)
    
    # Основные правила для русского языка
    last_char = name[-1].lower()
    stem = name[:-1]

    # Мужские имена на согласную
    if last_char in 'бвгджзклмнпрстфхцчшщ':
        return f'({re.escape(stem)}[аеиоуыэюя]{{0,2}}|{re.escape(name)}(а|у|ом|е|ы)?)'
    
    # Женские имена на -а/-я
    elif last_char == 'а':
        stem = name[:-1]
        return f'({re.escape(stem)}[еиую]|{re.escape(name[:-1])}ой|{re.escape(name)}|{stem}[еи]н)'
    
    elif last_char == 'я':
        stem = name[:-1]
        return f'({stem}е|{stem}ей|{stem}ю|{stem}и|{re.escape(name)})'
    
    # Несклоняемые имена
    return re.escape(name)


def get_character_name_variants(character: Character) -> list:
    """Возвращает все варианты имен персонажа с учетом склонений"""
    if not character or not character.name:
        return []
        
    variants = {character.name.lower()}
    
    # Добавляем варианты из базы данных
    if hasattr(character, 'name_variants') and character.name_variants:
        for variant in character.name_variants:
            if variant and hasattr(variant, 'variant') and variant.variant:
                variants.add(variant.variant.lower())
    
    # Генерируем склонения для каждого варианта
    all_variants = set()
    for name in variants:
        if name:
            all_variants.add(name)
            # Добавляем основные склонения
            all_variants.update(get_name_inflections(name))
    
    return list(all_variants)


# Вспомогательная функция для склонения имен
def get_name_inflections(name: str) -> list:
    """
    Создает варианты склонения имени для более точного поиска упоминаний
    """
    # Простой подход к склонениям для русских имен
    inflections = [name]  # Исходная форма
    
    # Если имя заканчивается на согласную (мужские имена)
    if name[-1].lower() in 'бвгджзйклмнпрстфхцчшщъь':
        inflections.extend([
            name + 'а',  # Родительный падеж (Ивана)
            name + 'у',  # Дательный падеж (Ивану)
            name + 'ом',  # Творительный падеж (Иваном)
            name + 'е'   # Предложный падеж (об Иване)
        ])
    # Если имя заканчивается на 'а' (женские имена)
    elif name[-1].lower() == 'а':
        stem = name[:-1]
        inflections.extend([
            stem + 'ы',  # Родительный падеж (Маши)
            stem + 'е',  # Дательный падеж (Маше)
            stem + 'у',  # Винительный падеж (Машу)
            stem + 'ой'  # Творительный падеж (Машей)
        ])
    # Если имя заканчивается на 'я' (женские имена)
    elif name[-1].lower() == 'я':
        stem = name[:-1]
        inflections.extend([
            stem + 'и',   # Родительный падеж (Тани)
            stem + 'е',   # Дательный падеж (Тане)
            stem + 'ю',   # Винительный падеж (Таню)
            stem + 'ей'   # Творительный падеж (Таней)
        ])
    
    return inflections

def get_chapter_content(chapter: Chapter) -> str:
    """Получает содержимое главы из файла"""
    try:
        content_path = Path(current_app.config['BOOKS_DIR']) / chapter.content_path
        if not content_path.exists():
            current_app.logger.error(f"Файл главы не найден: {content_path}")
            return ""
            
        with open(content_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    except Exception as e:
        current_app.logger.error(f"Ошибка чтения главы {chapter.id}: {str(e)}")
        return ""

def highlight_characters(content: str, characters: list) -> str:
    """
    Функция для выделения имен персонажей, их вариантов и склонений в HTML-контенте.
    Учитывает проблему составных имен, перекрытия вариантов имен и склонения имен в русском языке.
    """
    from html import escape
    
    # Создаем словарь с информацией о персонажах и их вариантах имен
    character_info = {}
    all_names = set()  # Множество всех возможных имен для проверки перекрытий
    
    for character in characters:
        # Получаем основное имя и варианты
        main_name = character.name
        variants = []
        
        if hasattr(character, 'name_variants') and character.name_variants:
            variants = [v.variant for v in character.name_variants if v.variant]
        
        # Сохраняем все имена для данного персонажа
        all_names.add(main_name)
        all_names.update(variants)
        
        # Сохраняем в словаре информацию о персонаже
        character_info[character.id] = {
            'main_name': main_name,
            'variants': variants,
            'all_forms': [main_name] + variants
        }
    
    # Создаем список шаблонов сопоставления, отсортированных по длине (от самых длинных к коротким)
    patterns = []
    for char_id, info in character_info.items():
        # Сортируем формы имен по длине в убывающем порядке
        sorted_forms = sorted(info['all_forms'], key=len, reverse=True)
        
        for form in sorted_forms:
            # Создаем базовую форму для поиска с учетом склонений
            # Используем корень имени (до последней гласной) + возможные окончания
            
            # Очищаем имя от кавычек и лишних символов
            clean_name = re.sub(r'[\'"`«»]', '', form)
            
            # Для русских имен создаем шаблон, учитывающий основные склонения
            # Этот подход работает для большинства русских имен
            # Например, "Иван" -> "Иван(а|у|ом|е|ы|ам|ами|ах)?"
            
            # Определяем, оканчивается ли имя на гласную
            vowels = 'аеёиоуыэюяАЕЁИОУЫЭЮЯ'
            consonants = 'бвгджзйклмнпрстфхцчшщъьБВГДЖЗЙКЛМНПРСТФХЦЧШЩЪЬ'
            
            # Логика для создания шаблона на основе окончания имени
            if len(clean_name) >= 3:  # Имя должно быть достаточно длинным для склонения
                # Пытаемся обнаружить корень имени
                if clean_name[-1] in vowels and clean_name[-2] in consonants:
                    # Имя типа "Иван", обрезаем последнюю букву для разных склонений
                    stem = clean_name[:-1]
                    pattern_str = re.escape(stem) + r'[аеиоыуюя]?'
                elif clean_name[-1] in consonants:
                    # Имя заканчивается на согласную, добавляем возможные окончания
                    pattern_str = re.escape(clean_name) + r'(а|у|ом|е|ы|ам|ами|ах)?'
                elif clean_name[-1] == 'а' or clean_name[-1] == 'я':
                    # Имя типа "Маша", "Катя" - женские имена
                    stem = clean_name[:-1]
                    pattern_str = re.escape(stem) + r'[аеиоуыюя]'
                elif len(clean_name.split()) > 1:
                    # Составное имя (напр. "Иван Петров") - обрабатываем каждую часть отдельно
                    name_parts = clean_name.split()
                    pattern_parts = []
                    
                    for part in name_parts:
                        if len(part) >= 3:
                            if part[-1] in vowels and part[-2] in consonants:
                                stem = part[:-1]
                                pattern_parts.append(re.escape(stem) + r'[аеиоыуюя]?')
                            elif part[-1] in consonants:
                                pattern_parts.append(re.escape(part) + r'(а|у|ом|е|ы|ам|ами|ах)?')
                            elif part[-1] == 'а' or part[-1] == 'я':
                                stem = part[:-1]
                                pattern_parts.append(re.escape(stem) + r'[аеиоуыюя]')
                            else:
                                pattern_parts.append(re.escape(part))
                        else:
                            pattern_parts.append(re.escape(part))
                    
                    pattern_str = r'\s+'.join(pattern_parts)
                else:
                    # Для других случаев используем точное совпадение
                    pattern_str = re.escape(clean_name)
            else:
                # Короткие имена и инициалы - используем точное совпадение
                pattern_str = re.escape(clean_name)
            
            # Используем границы слов для более точного совпадения
            pattern = re.compile(r'\b' + pattern_str + r'\b', re.IGNORECASE)
            patterns.append((pattern, char_id, form))
            
            # Логируем создаваемые шаблоны для отладки
            current_app.logger.debug(f"Created pattern for '{form}': {pattern_str}")
    
    # Сортируем паттерны по длине строки поиска (от длинных к коротким)
    patterns.sort(key=lambda x: len(x[2]), reverse=True)
    
    # Парсим HTML
    soup = BeautifulSoup(content, 'html.parser')
    
    # Функция для обработки текстового элемента
    def process_text_element(text_element):
        if text_element.parent.name in ['script', 'style']:
            return
            
        text = str(text_element)
        
        # Создаем список с найденными позициями всех совпадений
        matches = []
        for pattern, char_id, original_form in patterns:
            for match in pattern.finditer(text):
                start, end = match.span()
                matched_text = text[start:end]
                
                # Добавляем информацию о найденном совпадении
                matches.append((start, end, char_id, original_form, matched_text))
        
        # Если нет совпадений, просто выходим
        if not matches:
            return
            
        # Сортируем совпадения по начальной позиции
        matches.sort(key=lambda x: x[0])
        
        # Фильтруем перекрывающиеся совпадения
        filtered_matches = []
        marked_positions = set()
        
        for match in matches:
            start, end, char_id, form, matched_text = match
            
            # Проверяем, не перекрывается ли это совпадение с уже отмеченными
            overlap = False
            for pos in range(start, end):
                if pos in marked_positions:
                    overlap = True
                    break
            
            # Пропускаем перекрывающиеся совпадения
            if overlap:
                continue
                
            # Отмечаем позиции как обработанные
            for pos in range(start, end):
                marked_positions.add(pos)
                
            filtered_matches.append(match)
        
        # Строим новое содержимое, заменяя совпадения на span-элементы
        result = []
        last_pos = 0
        
        for start, end, char_id, form, matched_text in filtered_matches:
            # Добавляем текст до совпадения
            if start > last_pos:
                result.append(text[last_pos:start])
            
            # Добавляем span для персонажа
            # Обратите внимание: сохраняем оригинальное имя для data-attribute, но в тексте оставляем найденную форму
            result.append(f'<span class="character-highlight" data-character-id="{char_id}" data-original-name="{escape(form)}">{matched_text}</span>')
            
            last_pos = end
        
        # Добавляем оставшийся текст
        if last_pos < len(text):
            result.append(text[last_pos:])
        
        # Создаем новое содержимое и заменяем текстовый элемент
        new_content = BeautifulSoup(''.join(result), 'html.parser')
        text_element.replace_with(new_content)
    
    # Обрабатываем все текстовые элементы в документе
    for text_element in soup.find_all(text=True):
        process_text_element(text_element)
    
    return str(soup)

def add_name_variant(character_id: int, variant: str) -> int:
    """
    Добавляет вариант имени для персонажа
    Возвращает ID созданной записи
    """
    from app.models.book import NameVariant
    
    variant_record = NameVariant(
        character_id=character_id,
        variant=variant
    )
    db.session.add(variant_record)
    db.session.commit()
    return variant_record.id


def get_previous_chapters(book_id: int, current_chapter_number: int) -> List[Chapter]:
    """Получает все главы до текущей (не включая её)"""
    return Chapter.query.filter(
        Chapter.book_id == book_id,
        Chapter.number < current_chapter_number
    ).order_by(Chapter.number.asc()).all()


    
def process_chapter_for_characters(chapter_id: int, content: str):
    """
    Обрабатывает главу для извлечения упоминаний персонажей и сохраняет контекст в БД.
    Пропускает обработку, если глава уже помечена как обработанная.
    """
    try:
        # Получаем главу из БД
        chapter = get_chapter_by_id(chapter_id)
        
        # Проверяем условия для обработки
        if not chapter:
            current_app.logger.warning(f"Chapter {chapter_id} not found")
            return
            
        if chapter.is_processed:
            current_app.logger.info(f"Chapter {chapter_id} already processed, skipping")
            return
            
        if not content:
            current_app.logger.warning(f"Empty content for chapter {chapter_id}")
            return

        # Получаем всех персонажей книги
        characters = get_characters_by_book_id(chapter.book_id)
        if not characters:
            current_app.logger.info(f"No characters found for book {chapter.book_id}")
            return

        # Удаляем старые записи о появлениях персонажей
        try:
            deleted_count = CharacterAppearance.query.filter_by(chapter_id=chapter_id).delete()
            current_app.logger.info(f"Deleted {deleted_count} old appearances for chapter {chapter_id}")
        except Exception as delete_error:
            current_app.logger.error(f"Delete error for chapter {chapter_id}: {str(delete_error)}")
            db.session.rollback()
            return

        # Обрабатываем каждого персонажа
        processed_mentions = 0
        for character in characters:
            try:
                # Находим упоминания персонажа в тексте
                mentions = find_simple_mention(content, character)
                current_app.logger.debug(f"Found {len(mentions)} mentions for {character.name} in chapter {chapter_id}")

                # Сохраняем каждое упоминание
                for mention in mentions:
                    context = mention.get('context', '')
                    if not context.strip():
                        continue
                        
                    # Очищаем и обрезаем контекст для БД
                    cleaned_context = clean_text_for_db(context)
                    
                    # Создаем запись о появлении персонажа
                    appearance = CharacterAppearance(
                        character_id=character.id,
                        chapter_id=chapter_id,
                        context=cleaned_context
                    )
                    db.session.add(appearance)
                    processed_mentions += 1
                    
            except Exception as char_error:
                current_app.logger.error(f"Error processing character {character.id}: {str(char_error)}")
                continue

        # Помечаем главу как обработанную
        chapter.is_processed = True
        
        # Фиксируем изменения в БД
        db.session.commit()
        current_app.logger.info(f"Processed chapter {chapter_id}: {processed_mentions} mentions for {len(characters)} characters")

    except Exception as e:
        current_app.logger.error(f"Critical error processing chapter {chapter_id}: {str(e)}")
        db.session.rollback()
        raise


def clean_text_for_db(text: str) -> str:
    """Улучшенная очистка текста"""
    if not text:
        return ""
    
    # Удаление непечатаемых символов
    cleaned = ''.join(c for c in text if c.isprintable() or c in {'\n', '\t', '\r'})
    
    # Нормализация пробелов
    cleaned = ' '.join(cleaned.split())
    
    # Замена проблемных символов
    replacements = {
        '\ufeff': '',  # BOM
        '\x00': '',     # Null-байт
        '�': '',        # Replacement character
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    
    # Проверка максимальной длины
    max_length = 65535  # Для TEXT в MySQL
    return cleaned[:max_length] if len(cleaned) > max_length else cleaned

def verify_character_appearances(chapter_id: int):
    """
    Проверяет, что записи CharacterAppearance действительно сохранились
    """
    try:
        appearances = CharacterAppearance.query.filter_by(chapter_id=chapter_id).all()
        current_app.logger.info(f"Найдено {len(appearances)} записей для главы {chapter_id}")
        
        for appearance in appearances:
            character = get_character_by_id(appearance.character_id)
            context_preview = appearance.context[:50] + "..." if appearance.context and len(appearance.context) > 50 else appearance.context
            current_app.logger.info(f"- {character.name if character else 'Unknown'}: {context_preview}")
            
        return appearances
        
    except Exception as e:
        current_app.logger.error(f"Ошибка при проверке записей: {str(e)}")
        return []