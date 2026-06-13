"""
VidyaBot Database Schema & Initialization

Handles SQLite schema creation, connection pooling, and lifecycle management.
All data is stored in a single .db file for portability.
"""

import sqlite3
import os
import numpy as np
from pathlib import Path
from typing import Optional
from datetime import datetime
from backend.config import settings

# Global connection pool (simplified - production would use proper pooling)
_db_connection: Optional[sqlite3.Connection] = None


def get_db_connection() -> sqlite3.Connection:
    """Get or create database connection."""
    global _db_connection
    if _db_connection is None:
        db_path = settings.DB_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _db_connection = sqlite3.connect(db_path, check_same_thread=False)
        _db_connection.row_factory = sqlite3.Row  # Allow dict-like access
    return _db_connection


def init_db() -> None:
    """Initialize database schema. Idempotent — safe to call multiple times."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create textbooks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS textbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            title TEXT,
            board TEXT,
            subject TEXT,
            grade TEXT,
            total_pages INTEGER,
            total_chunks INTEGER,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create chunks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER REFERENCES textbooks(id) ON DELETE CASCADE,
            chapter_number INTEGER,
            chapter_title TEXT,
            section_title TEXT,
            page_number INTEGER,
            chunk_index INTEGER,
            content TEXT NOT NULL,
            token_count INTEGER,
            embedding BLOB,
            UNIQUE(textbook_id, chapter_number, chunk_index)
        )
    """)
    
    # Create BM25 index table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bm25_index (
            chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
            term TEXT,
            tf_idf REAL,
            PRIMARY KEY (chunk_id, term)
        )
    """)
    
    # Create query cache table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT UNIQUE NOT NULL,
            query_text TEXT NOT NULL,
            textbook_id INTEGER,
            language TEXT DEFAULT 'english',
            answer TEXT NOT NULL,
            context_tokens_used INTEGER,
            model_used TEXT,
            pruning_ratio REAL,
            source_pages TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_count INTEGER DEFAULT 0,
            last_accessed TIMESTAMP
        )
    """)
    
    # Create cost tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id INTEGER,
            textbook_id INTEGER,
            baseline_tokens INTEGER DEFAULT 2000,
            actual_tokens_used INTEGER,
            tokens_saved INTEGER,
            cost_usd REAL,
            cost_saved_usd REAL,
            cache_hit BOOLEAN DEFAULT 0,
            model_used TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create FAISS index metadata table (for tracking indexed textbooks)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faiss_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER UNIQUE REFERENCES textbooks(id) ON DELETE CASCADE,
            faiss_index_size INTEGER,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create BM25 metadata table (for tracking indexed textbooks)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bm25_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER UNIQUE REFERENCES textbooks(id) ON DELETE CASCADE,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # V2 UPGRADE TABLES — Curriculum routing + Sentence pruning + Teacher analytics
    
    # Chapter-level curriculum tags (added during ingestion)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chapter_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER REFERENCES textbooks(id) ON DELETE CASCADE,
            chapter_number INTEGER,
            subject_domain TEXT,
            bloom_levels TEXT,
            keywords TEXT,
            UNIQUE(textbook_id, chapter_number)
        )
    """)
    
    # Sentence-level pruning log (for analytics)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pruning_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id INTEGER,
            stage TEXT,
            chunks_in INTEGER,
            chunks_out INTEGER,
            tokens_in INTEGER,
            tokens_out INTEGER,
            latency_ms INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Teacher analytics cache (pre-computed daily)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER REFERENCES textbooks(id) ON DELETE CASCADE,
            date TEXT,
            top_questions TEXT,
            weak_chapters TEXT,
            hourly_usage TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add new columns to existing tables (if they don't exist)
    try:
        cursor.execute("ALTER TABLE chunks ADD COLUMN subject_domain TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE chunks ADD COLUMN bloom_level TEXT DEFAULT 'recall'")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE cost_log ADD COLUMN interface TEXT DEFAULT 'web'")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    print("[DB] Database schema initialized successfully")


def get_db() -> sqlite3.Connection:
    """Get database connection for use in routes."""
    return get_db_connection()


def close_db() -> None:
    """Close database connection."""
    global _db_connection
    if _db_connection:
        _db_connection.close()
        _db_connection = None


class Textbook:
    """DTO for textbook metadata."""
    def __init__(self, id: int, filename: str, title: str, board: str, 
                 subject: str, grade: str, total_pages: int, total_chunks: int,
                 ingested_at: str):
        self.id = id
        self.filename = filename
        self.title = title
        self.board = board
        self.subject = subject
        self.grade = grade
        self.total_pages = total_pages
        self.total_chunks = total_chunks
        self.ingested_at = ingested_at
    
    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "board": self.board,
            "subject": self.subject,
            "grade": self.grade,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "ingested_at": self.ingested_at
        }


class Chunk:
    """DTO for text chunks."""
    def __init__(self, id: int, textbook_id: int, chapter_number: int,
                 chapter_title: str, section_title: str, page_number: int,
                 chunk_index: int, content: str, token_count: int,
                 embedding_bytes: Optional[bytes] = None):
        self.id = id
        self.textbook_id = textbook_id
        self.chapter_number = chapter_number
        self.chapter_title = chapter_title
        self.section_title = section_title
        self.page_number = page_number
        self.chunk_index = chunk_index
        self.content = content
        self.token_count = token_count
        self._embedding_bytes = embedding_bytes
    
    @property
    def embedding(self) -> Optional[np.ndarray]:
        """Deserialize embedding from bytes."""
        if self._embedding_bytes is None:
            return None
        return np.frombuffer(self._embedding_bytes, dtype=np.float32)
    
    @embedding.setter
    def embedding(self, value: np.ndarray):
        """Serialize embedding to bytes."""
        if value is not None:
            self._embedding_bytes = value.astype(np.float32).tobytes()
        else:
            self._embedding_bytes = None
    
    def to_dict(self):
        return {
            "id": self.id,
            "textbook_id": self.textbook_id,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "token_count": self.token_count
        }


class PruningResult:
    """DTO for context pruning output."""
    def __init__(self, chunks: list, total_tokens: int, 
                 baseline_tokens: int = 2000, pruning_ratio: float = 0.0,
                 stage_timings: dict = None, stage_stats: dict = None):
        self.chunks = chunks
        self.total_tokens = total_tokens
        self.baseline_tokens = baseline_tokens
        self.pruning_ratio = pruning_ratio  # e.g., 0.80 = 80% reduction
        self.stage_timings = stage_timings or {}
        self.stage_stats = stage_stats or {}
        self.tokens_saved = baseline_tokens - total_tokens
    
    def to_dict(self):
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "total_tokens": self.total_tokens,
            "baseline_tokens": self.baseline_tokens,
            "tokens_saved": self.tokens_saved,
            "pruning_ratio": self.pruning_ratio,
            "stage_timings": self.stage_timings
        }


class CostLog:
    """DTO for cost tracking."""
    def __init__(self, query_id: int, baseline_tokens: int, actual_tokens_used: int,
                 cache_hit: bool = False, model_used: str = "claude-haiku-4-5-20251001"):
        self.query_id = query_id
        self.baseline_tokens = baseline_tokens
        self.actual_tokens_used = actual_tokens_used
        self.tokens_saved = baseline_tokens - actual_tokens_used
        self.cache_hit = cache_hit
        self.model_used = model_used
        
        # Calculate costs (Haiku pricing for Claude, 0 for local Ollama)
        is_ollama = (settings.LLM_BACKEND == "ollama") or ("claude" not in model_used.lower())
        if is_ollama:
            self.cost_usd = 0.0
        else:
            self.cost_usd = (actual_tokens_used / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M
            
        baseline_cost = (baseline_tokens / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M
        self.cost_saved_usd = baseline_cost - self.cost_usd
    
    def to_dict(self):
        return {
            "query_id": self.query_id,
            "baseline_tokens": self.baseline_tokens,
            "actual_tokens_used": self.actual_tokens_used,
            "tokens_saved": self.tokens_saved,
            "cost_usd": self.cost_usd,
            "cost_saved_usd": self.cost_saved_usd,
            "cache_hit": self.cache_hit,
            "model_used": self.model_used
        }


class LLMResponse:
    """DTO for LLM API responses."""
    def __init__(self, answer: str, input_tokens: int, output_tokens: int,
                 model: str = "claude-haiku-4-5-20251001"):
        self.answer = answer
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.model = model
        
        # Calculate cost
        is_ollama = (settings.LLM_BACKEND == "ollama") or ("claude" not in model.lower())
        if is_ollama:
            self.cost_usd = 0.0
        else:
            self.cost_usd = (
                (input_tokens / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M +
                (output_tokens / 1_000_000) * settings.HAIKU_OUTPUT_COST_PER_1M
            )
    
    def to_dict(self):
        return {
            "answer": self.answer,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "model": self.model
        }
