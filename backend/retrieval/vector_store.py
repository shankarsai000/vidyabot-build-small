"""
Vector Store Module

FAISS-based semantic search for Stage 2 of context pruning.
Reranks BM25 candidates using embedding similarity.
"""

import faiss
import numpy as np
import sqlite3
import os
import logging
from typing import List, Optional, Dict, Tuple
from backend.config import settings
from backend.database import get_db_connection, Chunk
from backend.ingestion.embedder import Embedder

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages FAISS vector index for semantic search."""
    
    def __init__(self):
        """Initialize vector store."""
        self.faiss_indices: Dict[int, faiss.IndexFlatIP] = {}  # textbook_id -> index
        self.chunk_id_maps: Dict[int, List[int]] = {}  # textbook_id -> [chunk_ids]
        self.embedder = Embedder()
    
    def build_index(self, textbook_id: int, chunks: List[Chunk]) -> None:
        """
        Build FAISS index from chunk embeddings.
        
        Stage 2: Semantic reranker
        - Input: top-30 BM25 candidates
        - Output: top-10 semantically similar chunks
        - Cost: local inference only (~5ms)
        
        Args:
            textbook_id: ID of textbook
            chunks: List of Chunk objects (must have embeddings)
        """
        if not chunks:
            logger.warning(f"No chunks to index for textbook {textbook_id}")
            return
        
        logger.info(f"Building FAISS index for textbook {textbook_id} with {len(chunks)} chunks")
        
        # Extract embeddings from chunks
        embeddings = []
        chunk_ids = []
        
        for chunk in chunks:
            if chunk.embedding is not None:
                # Normalize embedding for cosine similarity
                embedding = self.embedder.normalize_embeddings(np.array([chunk.embedding]))[0]
                embeddings.append(embedding)
                chunk_ids.append(chunk.id)
            else:
                logger.warning(f"Chunk {chunk.id} has no embedding, skipping")
        
        if not embeddings:
            logger.warning(f"No embeddings found for textbook {textbook_id}")
            return
        
        # Convert to float32 array
        embeddings_array = np.array(embeddings, dtype=np.float32)
        
        # Create FAISS index with inner-product (cosine similarity for normalized vectors)
        dimension = embeddings_array.shape[1]  # Should be 384 for MiniLM
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings_array)
        
        # Store in memory and database
        self.faiss_indices[textbook_id] = index
        self.chunk_id_maps[textbook_id] = chunk_ids
        
        logger.info(f"✅ FAISS index built. Dimension: {dimension}, Chunks: {len(chunk_ids)}")
        
        # Store metadata in database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO faiss_metadata (textbook_id, faiss_index_size, indexed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (textbook_id, len(chunk_ids)))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error storing FAISS metadata: {e}")
    
    def search(self, query_embedding: np.ndarray, textbook_id: int,
              candidate_chunk_ids: Optional[List[int]] = None, 
              top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Search for semantically similar chunks.
        
        Can search:
        1. All chunks in textbook (if candidate_chunk_ids is None)
        2. Only specific candidates (if candidate_chunk_ids provided - preferred for Stage 2)
        
        Args:
            query_embedding: Embedded query (1D array, shape (384,))
            textbook_id: Textbook ID
            candidate_chunk_ids: Optional list of candidate chunk IDs to search within
            top_k: Number of top results to return
            
        Returns:
            List of tuples (chunk_id, similarity_score) sorted by score descending
        """
        try:
            # Normalize query embedding
            query_embedding = self.embedder.normalize_embeddings(
                np.array([query_embedding], dtype=np.float32)
            )[0]
            
            # Get FAISS index for textbook
            if textbook_id not in self.faiss_indices:
                logger.warning(f"No FAISS index for textbook {textbook_id}")
                return []
            
            index = self.faiss_indices[textbook_id]
            chunk_ids = self.chunk_id_maps[textbook_id]
            
            # Search
            query_reshaped = query_embedding.reshape(1, -1)
            scores, indices = index.search(query_reshaped, min(top_k * 2, len(chunk_ids)))
            
            results = []
            for idx, score in zip(indices[0], scores[0]):
                if idx < len(chunk_ids):
                    chunk_id = chunk_ids[idx]
                    
                    # Filter by candidates if provided (Stage 2: rerank BM25 results)
                    if candidate_chunk_ids is None or chunk_id in candidate_chunk_ids:
                        results.append((chunk_id, float(score)))
                        
                        if len(results) >= top_k:
                            break
            
            logger.debug(f"Semantic search returned {len(results)} chunks for textbook {textbook_id}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    def search_from_db(self, query_embedding: np.ndarray, textbook_id: int,
                       candidate_chunk_ids: Optional[List[int]] = None,
                       top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Search using embeddings stored in database.
        Falls back when in-memory index isn't available.
        
        Args:
            query_embedding: Query embedding
            textbook_id: Textbook ID
            candidate_chunk_ids: Optional candidate filter
            top_k: Number of results
            
        Returns:
            List of (chunk_id, similarity_score) tuples
        """
        try:
            query_embedding = self.embedder.normalize_embeddings(
                np.array([query_embedding], dtype=np.float32)
            )[0]
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get all chunks' embeddings from database
            if candidate_chunk_ids:
                placeholders = ','.join('?' * len(candidate_chunk_ids))
                cursor.execute(f"""
                    SELECT id, embedding FROM chunks
                    WHERE textbook_id = ? AND id IN ({placeholders})
                """, [textbook_id] + candidate_chunk_ids)
            else:
                cursor.execute("""
                    SELECT id, embedding FROM chunks
                    WHERE textbook_id = ?
                """, (textbook_id,))
            
            rows = cursor.fetchall()
            
            results = []
            for chunk_id, embedding_bytes in rows:
                if embedding_bytes:
                    chunk_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                    
                    # Compute similarity
                    similarity = self.embedder.similarity(query_embedding, chunk_embedding)
                    results.append((chunk_id, similarity))
            
            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Error in database semantic search: {e}")
            return []
    
    def add_embeddings(self, textbook_id: int, chunks: List[Chunk]) -> None:
        """
        Add embeddings to chunks in database.
        
        Args:
            textbook_id: Textbook ID
            chunks: List of chunks with content (embeddings will be computed)
        """
        logger.info(f"Computing embeddings for {len(chunks)} chunks")
        
        # Extract texts from chunks
        texts = [chunk.content for chunk in chunks]
        
        # Generate embeddings
        embeddings = self.embedder.embed_chunks(texts, show_progress=True)
        
        # Store in database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            for chunk, embedding in zip(chunks, embeddings):
                embedding_bytes = embedding.astype(np.float32).tobytes()
                
                cursor.execute("""
                    UPDATE chunks
                    SET embedding = ?
                    WHERE id = ?
                """, (embedding_bytes, chunk.id))
            
            conn.commit()
            logger.info(f"✅ Embeddings stored for {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Error storing embeddings: {e}")
    
    def load_index(self, textbook_id: int) -> bool:
        """
        Load FAISS index from database if not already in memory.
        
        Args:
            textbook_id: Textbook ID
            
        Returns:
            True if successfully loaded, False otherwise
        """
        # If already in memory, no need to reload
        if textbook_id in self.faiss_indices:
            return True
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get all chunks with embeddings for this textbook
            cursor.execute("""
                SELECT id, embedding FROM chunks
                WHERE textbook_id = ? AND embedding IS NOT NULL
                ORDER BY chunk_index ASC
            """, (textbook_id,))
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning(f"No embeddings found for textbook {textbook_id}")
                return False
            
            # Reconstruct index
            embeddings = []
            chunk_ids = []
            
            for chunk_id, embedding_bytes in rows:
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                embeddings.append(embedding)
                chunk_ids.append(chunk_id)
            
            embeddings_array = np.array(embeddings, dtype=np.float32)
            
            # Create FAISS index
            dimension = embeddings_array.shape[1]
            index = faiss.IndexFlatIP(dimension)
            index.add(embeddings_array)
            
            self.faiss_indices[textbook_id] = index
            self.chunk_id_maps[textbook_id] = chunk_ids
            
            logger.info(f"✅ Loaded FAISS index for textbook {textbook_id}: {len(chunk_ids)} chunks")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
            return False
    
    @staticmethod
    def clear_index(textbook_id: int) -> None:
        """
        Clear FAISS metadata for a textbook.
        
        Args:
            textbook_id: Textbook ID
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM faiss_metadata WHERE textbook_id = ?", (textbook_id,))
            conn.commit()
            
            logger.info(f"✅ FAISS metadata cleared for textbook {textbook_id}")
            
        except Exception as e:
            logger.error(f"Error clearing FAISS metadata: {e}")
