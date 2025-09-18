from pathlib import Path
from app.config import Config
from app.services.parser import parse_and_save_epub
from app import db

def initialize_existing_books():
    """Автоматически загружает EPUB-файлы"""
    books_dir = Config.BOOKS_DIR
    
    for epub_path in books_dir.rglob('*.epub'):
        try:
            # Явно создаем новую сессию для каждой книги
            with db.session.begin():
                book_id = parse_and_save_epub(str(epub_path))
                print(f"Loaded: {epub_path.name} (ID: {book_id})")
        except Exception as e:
            print(f"Error loading {epub_path.name}: {str(e)}")
            db.session.rollback()