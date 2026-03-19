"""
BM25 Index Module

Builds and searches BM25 keyword index for fast pre-filtering.
Stage 1 of the 3-stage context pruning pipeline.
"""

from typing import List, Dict, Set, Tuple, Optional
from rank_bm25 import BM25Okapi
import sqlite3
import logging
from backend.config import settings
from backend.database import get_db_connection, Chunk

logger = logging.getLogger(__name__)


class BM25Index:
    """Manages BM25 keyword indexing and search."""
    
    # Optional: use NLTK for better tokenization (commented out to minimize dependencies)
    # from nltk.corpus import stopwords
    # STOP_WORDS = set(stopwords.words('english'))
    
    # Simple English stopwords + common Indian words
    STOP_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'if', 'as', 'of', 'to', 'in', 'is',
        'was', 'has', 'have', 'had', 'are', 'be', 'that', 'this', 'which', 'who',
        'what', 'where', 'when', 'why', 'how', 'on', 'at', 'by', 'from', 'up',
        'with', 'for', 'into', 'about', 'than', 'such', 'so', 'its', 'just',
        'do', 'does', 'did', 'doing', 'done', 'should', 'could', 'would', 'can',
        # Common Indian words
        'chapter', 'page', 'section', 'figure', 'table', 'exercise'
    }
    
    def __init__(self):
        """Initialize BM25 index."""
        self.bm25 = None
        self.chunk_ids = []
    
    def build_index(self, textbook_id: int, chunks: List[Chunk]) -> None:
        """
        Build BM25 index from chunks and store in database.
        
        Stage 1: BM25 keyword filter
        - Input: all chunks (~400+ per textbook)
        - Output: top-30 chunks by keyword overlap
        - Cost: zero (local computation)
        
        Args:
            textbook_id: ID of textbook being indexed
            chunks: List of Chunk objects with content
        """
        if not chunks:
            logger.warning(f"No chunks to index for textbook {textbook_id}")
            return
        
        logger.info(f"Building BM25 index for textbook {textbook_id} with {len(chunks)} chunks")
        
        # Tokenize all chunks
        tokenized_chunks = []
        self.chunk_ids = []
        
        for chunk in chunks:
            tokens = self._tokenize(chunk.content)
            tokenized_chunks.append(tokens)
            self.chunk_ids.append(chunk.id)
        
        # Build BM25 model
        self.bm25 = BM25Okapi(tokenized_chunks)
        
        # Store in database for persistence
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Compute BM25 scores for each term in each chunk
            for chunk_idx, chunk in enumerate(chunks):
                tokens = tokenized_chunks[chunk_idx]
                
                # Compute BM25 scores for unique terms
                for term in set(tokens):
                    # Calculate IDF and BM25 contribution
                    doc_freq = self.bm25.idf[term]  # Inverse document frequency
                    score = doc_freq  # Simplified: just use IDF as score
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO bm25_index (chunk_id, term, tf_idf)
                        VALUES (?, ?, ?)
                    """, (chunk.id, term, score))
            
            conn.commit()
            logger.info(f"✅ BM25 index stored for textbook {textbook_id}")
            
            # Mark as indexed
            cursor.execute("""
                INSERT OR REPLACE INTO bm25_metadata (textbook_id, indexed_at)
                VALUES (?, CURRENT_TIMESTAMP)
            """, (textbook_id,))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error storing BM25 index: {e}")
    
    def search(self, query: str, textbook_id: int, top_k: int = 30) -> List[int]:
        """
        Search for relevant chunks using BM25.
        
        Args:
            query: Search query
            textbook_id: ID of textbook to search in
            top_k: Number of top results to return (Stage 1 typically returns 30)
            
        Returns:
            List of chunk IDs, sorted by BM25 score (highest first)
        """
        # Tokenize query
        query_tokens = self._tokenize(query)
        
        if not query_tokens or self.bm25 is None:
            # Fallback: return empty list (will fall through to semantic search)
            return self._fallback_search(textbook_id, top_k)
        
        try:
            # Get BM25 scores for this query
            scores = self.bm25.get_scores(query_tokens)
            
            # Get top-k chunks by score
            if scores is None or len(scores) == 0:
                return self._fallback_search(textbook_id, top_k)
            
            # Get indices of top scores
            top_indices = sorted(
                range(len(scores)),
                key=lambda i: scores[i],
                reverse=True
            )[:top_k]
            
            # Map indices back to chunk IDs
            result_chunk_ids = [self.chunk_ids[i] for i in top_indices if i < len(self.chunk_ids)]
            
            logger.debug(f"BM25 search returned {len(result_chunk_ids)} chunks for query: {query[:50]}")
            
            return result_chunk_ids
            
        except Exception as e:
            logger.error(f"Error in BM25 search: {e}")
            return self._fallback_search(textbook_id, top_k)
    
    def search_from_db(self, query: str, textbook_id: int, top_k: int = 30) -> List[int]:
        """
        Search using BM25 index stored in database.
        This is useful when the in-memory index isn't available.
        
        Args:
            query: Search query
            textbook_id: Textbook ID
            top_k: Number of results
            
        Returns:
            List of chunk IDs
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get unique chunks from bm25_index that match query terms
            query_tokens = self._tokenize(query)
            
            if not query_tokens:
                return []
            
            # Placeholder search: get top chunks by term frequency
            placeholders = ','.join('?' * len(query_tokens))
            
            cursor.execute(f"""
                SELECT chunk_id, SUM(tf_idf) as total_score
                FROM bm25_index
                WHERE term IN ({placeholders})
                AND chunk_id IN (
                    SELECT id FROM chunks WHERE textbook_id = ?
                )
                GROUP BY chunk_id
                ORDER BY total_score DESC
                LIMIT ?
            """, query_tokens + [textbook_id, top_k])
            
            results = cursor.fetchall()
            return [row[0] for row in results]
            
        except Exception as e:
            logger.error(f"Error in database BM25 search: {e}")
            return []
    
    def _fallback_search(self, textbook_id: int, top_k: int = 30) -> List[int]:
        """
        Fallback search when BM25 fails - just return first N chunks.
        
        Args:
            textbook_id: Textbook ID
            top_k: Number of chunks to return
            
        Returns:
            List of chunk IDs
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM chunks
                WHERE textbook_id = ?
                ORDER BY page_number ASC, chunk_index ASC
                LIMIT ?
            """, (textbook_id, top_k))
            
            results = cursor.fetchall()
            return [row[0] for row in results]
            
        except Exception as e:
            logger.error(f"Error in fallback search: {e}")
            return []
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization: lowercase, split, remove stopwords.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        # Lowercase and split
        tokens = text.lower().split()
        
        # Remove punctuation and filter stopwords
        cleaned_tokens = []
        for token in tokens:
            # Remove punctuation
            token = ''.join(c for c in token if c.isalnum())
            
            # Skip short tokens and stopwords
            if len(token) > 2 and token not in self.STOP_WORDS:
                cleaned_tokens.append(token)
        
        return cleaned_tokens
    
    @staticmethod
    def clear_index(textbook_id: int) -> None:
        """
        Clear BM25 index for a textbook from database.
        
        Args:
            textbook_id: Textbook ID
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get all chunk IDs for this textbook
            cursor.execute("SELECT id FROM chunks WHERE textbook_id = ?", (textbook_id,))
            chunk_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete from bm25_index
            for chunk_id in chunk_ids:
                cursor.execute("DELETE FROM bm25_index WHERE chunk_id = ?", (chunk_id,))
            
            cursor.execute("DELETE FROM bm25_metadata WHERE textbook_id = ?", (textbook_id,))
            conn.commit()
            
            logger.info(f"✅ BM25 index cleared for textbook {textbook_id}")
            
        except Exception as e:
            logger.error(f"Error clearing BM25 index: {e}")
