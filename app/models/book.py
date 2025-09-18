# -*- coding: utf-8 -*-
# Модели для работы с книгами и персонажами.
from app import db
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict
from sqlalchemy import text


def utf8mb4_column(length=None):
    return db.String(length, collation='utf8mb4_unicode_ci') if length else db.Text(collation='utf8mb4_unicode_ci')

class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    processed = db.Column(db.Boolean, default=False)
    element_type = db.Column(utf8mb4_column(50))  # Том, Часть, Глава, Действие, Явление
    hierarchy_level = db.Column(db.Integer)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('chapters.id', ondelete='CASCADE'))
    title = db.Column(utf8mb4_column(300))
    number = db.Column(db.Integer)
    content_path = db.Column(utf8mb4_column(500))
    is_parent = db.Column(db.Boolean, default=False)
    is_processed = db.Column(db.Boolean, default=False)

    # Иерархия глав
    children = db.relationship(
        'Chapter',
        backref=db.backref('parent', remote_side=[id]),
        lazy='joined',
        order_by='Chapter.number',
        cascade='all, delete-orphan'
    )
    
    character_appearances = db.relationship(
        'CharacterAppearance',
        back_populates='chapter',
        lazy='dynamic',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    __table_args__ = (
        db.UniqueConstraint('book_id', 'content_path', name='uq_book_content'),
        db.UniqueConstraint('book_id', 'parent_id', 'title', name='uq_book_parent_title'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    )


    def __repr__(self):
        return f'<Chapter {self.number}: {self.title}>'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'book_id': self.book_id,
            'parent_id': self.parent_id,
            'title': self.title,
            'number': self.number,
            'content_path': self.content_path,
            'is_parent': self.is_parent
        }
    @property
    def first_content_chapter(self):
        """
        Возвращает первую дочернюю главу с контентом, рекурсивно проверяя детей
        Если у текущей главы есть контент - возвращает себя
        """
        if self.content_path:
            return self
        for child in sorted(self.children, key=lambda x: x.number):
            result = child.first_content_chapter
            if result:
                return result
        return None
    @property
    def display_number(self):
        """Форматированный номер главы с учетом иерархии"""
        if self.parent:
            return f"{self.parent.display_number}.{self.number}"
        return str(self.number)
    
    @property
    def display_title(self):
        """Возвращает заголовок главы с номером"""
        if self.title:
            return f"{self.display_number}. {self.title}"
        return f"Глава {self.display_number}"

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(utf8mb4_column(255), nullable=False, index=True)
    author = db.Column(utf8mb4_column(255), nullable=False, index=True)
    filename = db.Column(utf8mb4_column(255), nullable=False, unique=True)
    cover_path = db.Column(utf8mb4_column(255), nullable=True)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Отношения
    characters = db.relationship('Character', backref='book', lazy=True, cascade='all, delete-orphan', passive_deletes=True)
    chapters = db.relationship('Chapter', backref='book', lazy=True, cascade='all, delete-orphan', passive_deletes=True)

    __table_args__ = {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}

    def __repr__(self) -> str:
        return f'<Book {self.title} by {self.author}>'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'filename': self.filename,
            'cover_path': self.cover_path,
            'added_date': self.added_date.isoformat() if self.added_date else None
        }

class NameVariant(db.Model):
    __tablename__ = 'name_variants'
    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey('characters.id', ondelete='CASCADE'), nullable=False)
    variant = db.Column(utf8mb4_column(255), nullable=False, index=True)

    __table_args__ = (
        db.Index('ix_variant', text('variant(191)')),  # Для обхода ограничения длины индекса
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    )

    def __repr__(self):
        return f'<NameVariant {self.variant} for character {self.character_id}>'

    
class Character(db.Model):
    __tablename__ = 'characters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(utf8mb4_column(255), nullable=False)
    word_boundary = db.Column(db.Boolean, default=True)
    split_words = db.Column(db.Boolean, default=False)
    custom_pattern = db.Column(utf8mb4_column(200))

    name_variants = db.relationship(
        'NameVariant', 
        backref='character', 
        lazy=True,
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    appearances = db.relationship(
        'CharacterAppearance', 
        back_populates='character',
        lazy=True,
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    __table_args__ = {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}

    def __repr__(self) -> str:
        return f'<Character {self.name} from book_id {self.book_id}>'

class CharacterAppearance(db.Model):
    __tablename__ = 'character_appearances'
    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey('characters.id', ondelete='CASCADE'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False)
    context = db.Column(db.Text(collation='utf8mb4_unicode_ci'))

    character = db.relationship('Character', back_populates='appearances')
    chapter = db.relationship('Chapter', back_populates='character_appearances')

    __table_args__ = (
        db.Index('ix_character_chapter', 'character_id', 'chapter_id'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    )

    def __repr__(self) -> str:
        return f'<Appearance {self.character_id} in {self.chapter_id}>'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'character_id': self.character_id,
            'chapter_id': self.chapter_id,
            'context': self.context
        }
    
class ChapterSummary(db.Model):
    __tablename__ = 'chapter_summaries'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id', ondelete='CASCADE'), index=True)
    character_id = db.Column(db.Integer, db.ForeignKey('characters.id', ondelete='CASCADE'), index=True)
    summary = db.Column(db.Text(collation='utf8mb4_unicode_ci'), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    analysis_version = db.Column(utf8mb4_column(20))

    __table_args__ = (
        db.UniqueConstraint('chapter_id', 'character_id', name='uq_chapter_character'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
    )
    
    def __repr__(self):
        return f'<ChapterSummary {self.chapter_id}-{self.character_id}>'
    
