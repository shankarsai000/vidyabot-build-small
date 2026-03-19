"""
PDF Ingestion Routes

POST /api/ingest - Upload and ingest PDF textbooks
GET /api/textbooks - List all ingested textbooks
"""

import asyncio
import logging
import os
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
import tempfile
import time
from typing import Dict, List

from backend.ingestion.pdf_parser import PDFParser
from backend.ingestion.chunker import Chunker, TextChunk
from backend.ingestion.embedder import Embedder
from backend.database import get_db_connection, Textbook
from backend.retrieval.context_pruner import ContextPruner
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingestion"])


@router.get("/textbooks")
async def list_textbooks() -> Dict:
    """
    Get list of all ingested textbooks with metadata.
    
    Returns:
        JSON with list of textbooks
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, filename, title, board, subject, grade, total_pages,
                   total_chunks, ingested_at
            FROM textbooks
            ORDER BY ingested_at DESC
        """)
        
        rows = cursor.fetchall()
        
        textbooks = [
            {
                "id": row[0],
                "filename": row[1],
                "title": row[2],
                "board": row[3],
                "subject": row[4],
                "grade": row[5],
                "total_pages": row[6],
                "total_chunks": row[7],
                "ingested_at": row[8]
            }
            for row in rows
        ]
        
        return {
            "status": "success",
            "textbooks": textbooks,
            "count": len(textbooks)
        }
        
    except Exception as e:
        logger.error(f"Error listing textbooks: {e}")
        return {
            "status": "error",
            "message": str(e),
            "textbooks": []
        }


@router.post("/ingest")
async def ingest_pdf(
    file: UploadFile = File(...),
    board: str = Form(...),
    subject: str = Form(...),
    grade: str = Form(...),
    title: str = Form(...),
    background_tasks: BackgroundTasks = None
) -> Dict:
    """
    Upload and ingest a PDF textbook.
    
    Args:
        file: PDF file upload
        board: Board (CBSE, SSLC, NCERT, Maharashtra, etc.)
        subject: Subject name
        grade: Grade level
        title: Textbook title
        background_tasks: Background task queue (for index building)
    
    Returns:
        JSON with ingestion results
    """
    start_time = time.time()
    temp_path = None
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            contents = await file.read()
            tmp.write(contents)
            temp_path = tmp.name
        
        logger.info(f"Ingesting {file.filename} ({len(contents)} bytes)")
        
        # Parse PDF
        parser = PDFParser(temp_path)
        parsed_pages = parser.parse()
        pdf_metadata = parser.get_metadata()
        
        logger.info(f"Parsed {len(parsed_pages)} pages from {file.filename}")
        
        # Chunk text
        chunker = Chunker(
            max_chunk_tokens=settings.CHUNK_MAX_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS
        )
        chunks = chunker.chunk_by_section(parsed_pages)
        
        logger.info(f"Created {len(chunks)} chunks")
        
        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert textbook metadata
        cursor.execute("""
            INSERT INTO textbooks
            (filename, title, board, subject, grade, total_pages, total_chunks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            file.filename,
            title or pdf_metadata.get("title", file.filename),
            board,
            subject,
            grade,
            len(parsed_pages),
            len(chunks)
        ))
        conn.commit()
        
        # Get textbook ID
        cursor.execute("SELECT last_insert_rowid()")
        textbook_id = cursor.fetchone()[0]
        
        logger.info(f"Created textbook ID {textbook_id}")
        
        # Insert chunks
        for chunk in chunks:
            chunk.textbook_id = textbook_id
            
            cursor.execute("""
                INSERT INTO chunks
                (textbook_id, chapter_number, chapter_title, section_title,
                 page_number, chunk_index, content, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.textbook_id,
                chunk.chapter_number,
                chunk.chapter_title,
                chunk.section_title,
                chunk.page_number,
                chunk.chunk_index,
                chunk.content,
                chunk.token_count
            ))
        conn.commit()
        
        logger.info(f"Stored {len(chunks)} chunks in database")
        
        # Add embeddings
        embedder = Embedder()
        texts = [chunk.content for chunk in chunks]
        embeddings = embedder.embed_chunks(texts, show_progress=True)
        
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            embedding_bytes = embedding.astype('float32').tobytes()
            
            cursor.execute("""
                UPDATE chunks SET embedding = ? WHERE textbook_id = ? AND chunk_index = ?
            """, (embedding_bytes, textbook_id, chunk.chunk_index))
        conn.commit()
        
        logger.info("Stored embeddings")
        
        # Setup pruning indexes in background
        if background_tasks:
            background_tasks.add_task(
                _setup_indexes_background,
                textbook_id
            )
        else:
            _setup_indexes_background(textbook_id)
        
        elapsed = time.time() - start_time
        
        return {
            "status": "success",
            "textbook_id": textbook_id,
            "total_chunks": len(chunks),
            "processing_time_seconds": elapsed,
            "title": title,
            "board": board,
            "subject": subject,
            "grade": grade
        }
        
    except Exception as e:
        logger.error(f"Error ingesting PDF: {e}")
        return {
            "status": "error",
            "message": str(e),
            "textbook_id": None
        }
    
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Could not delete temp file: {e}")


def _setup_indexes_background(textbook_id: int) -> None:
    """
    Build BM25 and FAISS indexes in background.
    Called after PDF ingestion completes.
    
    Args:
        textbook_id: Textbook ID to index
    """
    try:
        logger.info(f"Setting up indexes for textbook {textbook_id}")
        
        pruner = ContextPruner()
        pruner.setup_textbook(textbook_id)
        
        logger.info(f"✅ Indexes ready for textbook {textbook_id}")
        
    except Exception as e:
        logger.error(f"Error setting up indexes: {e}")
