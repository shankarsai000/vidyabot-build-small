"""
Semantic Cache Module

Query deduplication using embedding similarity.
Caches answers to semantically similar questions.

Benefits:
- Identical queries: cached (similarity = 1.0)
- Near-identical queries: cached (similarity > 0.90)
- Similar intent queries: cached (similarity > threshold)
- Saves ~0% tokens on first query, ~0% on cache miss, 100% on cache hit
"""

import hashlib
import logging
import faiss
import numpy as np
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from backend.config import settings
from backend.database import get_db_connection
from backend.ingestion.embedder import Embedder

logger = logging.getLogger(__name__)


@dataclass
class CachedAnswer:
    """Represents a cached query/answer pair."""
    query_id: int
    query_text: str
    query_embedding: np.ndarray
    answer: str
    context_tokens_used: int
    model_used: str
    pruning_ratio: float
    source_pages: str
    created_at: str
    accessed_count: int = 0
    

class SemanticCache:
    """Manages query cache with embedding-based semantic similarity."""
    
    def __init__(self):
        """Initialize semantic cache."""
        self.embedder = Embedder()
        self.faiss_index: Optional[faiss.IndexFlatIP] = None
        self.cached_queries: Dict[int, CachedAnswer] = {}  # id -> CachedAnswer
        self.query_order: list = []  # Tracks insertion order for LRU
    
    def load_cache(self) -> None:
        """
        Load cached queries from database into memory FAISS index.
        Run on application startup.
        """
        logger.info("Loading semantic cache from database...")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get all cached queries
            cursor.execute("""
                SELECT id, query_text, answer, context_tokens_used, model_used,
                       pruning_ratio, source_pages, created_at, accessed_count
                FROM query_cache
                ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.info("Cache is empty")
                self.faiss_index = faiss.IndexFlatIP(settings.EMBEDDINGS_DIMENSION)
                return
            
            # Embed all cached queries
            query_texts = [row[1] for row in rows]
            embeddings = self.embedder.embed_chunks(query_texts, show_progress=True)
            embeddings = self.embedder.normalize_embeddings(embeddings)
            
            # Create FAISS index
            self.faiss_index = faiss.IndexFlatIP(settings.EMBEDDINGS_DIMENSION)
            self.faiss_index.add(embeddings)
            
            # Load into memory cache
            for i, row in enumerate(rows):
                cache_item = CachedAnswer(
                    query_id=row[0],
                    query_text=row[1],
                    query_embedding=embeddings[i],  # Save embedding for later
                    answer=row[2],
                    context_tokens_used=row[3],
                    model_used=row[4],
                    pruning_ratio=row[5],
                    source_pages=row[6],
                    created_at=row[7],
                    accessed_count=row[8]
                )
                
                self.cached_queries[row[0]] = cache_item
                self.query_order.append(row[0])
            
            logger.info(f"✅ Loaded {len(self.cached_queries)} cached queries")
            
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self.faiss_index = faiss.IndexFlatIP(settings.EMBEDDINGS_DIMENSION)
    
    def check_cache(self, query: str, textbook_id: int) -> Optional[Dict]:
        """
        Check if query exists in cache (with semantic similarity).
        
        Args:
            query: Student question
            textbook_id: Textbook being searched
            
        Returns:
            Cached answer dict if found, None otherwise
        """
        if self.faiss_index is None or len(self.cached_queries) == 0:
            return None
        
        try:
            # Embed query
            query_embedding = self.embedder.embed_query(query)
            query_embedding = self.embedder.normalize_embeddings(
                np.array([query_embedding], dtype=np.float32)
            )[0]
            
            # Search FAISS index
            query_reshaped = query_embedding.reshape(1, -1)
            distances, indices = self.faiss_index.search(query_reshaped, 1)
            
            if len(indices) == 0 or len(indices[0]) == 0:
                return None
            
            # For IndexFlatIP with normalized vectors, distance = similarity score
            similarity = float(distances[0][0])
            best_idx = int(indices[0][0])
            
            logger.debug(f"Best cache match similarity: {similarity:.3f} (threshold: {settings.CACHE_SIMILARITY_THRESHOLD})")
            
            # Check if above threshold
            if similarity < settings.CACHE_SIMILARITY_THRESHOLD:
                return None
            
            # Get cached answer
            query_ids = list(self.cached_queries.keys())
            if best_idx >= len(query_ids):
                return None
            
            query_id = query_ids[best_idx]
            cached = self.cached_queries[query_id]
            
            # Update access statistics
            cached.accessed_count += 1
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE query_cache
                    SET accessed_count = ?, last_accessed = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (cached.accessed_count, query_id))
                conn.commit()
            except Exception as e:
                logger.warning(f"Error updating cache access: {e}")
            
            logger.info(f"✅ Cache hit! Similarity: {similarity:.3f}, Saved {cached.context_tokens_used} tokens")
            
            return {
                "query_id": query_id,
                "answer": cached.answer,
                "context_tokens_used": cached.context_tokens_used,
                "model_used": cached.model_used,
                "pruning_ratio": cached.pruning_ratio,
                "source_pages": cached.source_pages,
                "cache_hit": True,
                "similarity": similarity,
                "accessed_count": cached.accessed_count
            }
            
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None
    
    def store_in_cache(self, query: str, answer: str, context_tokens_used: int,
                      textbook_id: int, model_used: str, pruning_ratio: float,
                      source_pages: str) -> int:
        """
        Store query/answer pair in cache.
        
        Args:
            query: Original query
            answer: LLM answer
            context_tokens_used: Tokens used for this query
            textbook_id: Textbook ID
            model_used: Model name
            pruning_ratio: Token reduction ratio
            source_pages: Comma-separated page numbers
            
        Returns:
            Query cache ID
        """
        try:
            # Embed query
            query_embedding = self.embedder.embed_query(query)
            query_embedding = self.embedder.normalize_embeddings(
                np.array([query_embedding], dtype=np.float32)
            )[0]
            
            # Store in database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Generate query hash for deduplication
            query_hash = hashlib.sha256(query.lower().encode()).hexdigest()
            
            cursor.execute("""
                INSERT INTO query_cache
                (query_hash, query_text, textbook_id, answer, context_tokens_used,
                 model_used, pruning_ratio, source_pages)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_hash) DO UPDATE SET
                    accessed_count = accessed_count + 1,
                    last_accessed = CURRENT_TIMESTAMP
            """, (query_hash, query, textbook_id, answer, context_tokens_used,
                  model_used, pruning_ratio, source_pages))
            conn.commit()
            
            # Get inserted ID
            cursor.execute("SELECT id FROM query_cache WHERE query_hash = ?", (query_hash,))
            cache_id = cursor.fetchone()[0]
            
            # Add to FAISS index if not already there
            if self.faiss_index.ntotal == 0:
                # Create new index
                self.faiss_index = faiss.IndexFlatIP(settings.EMBEDDINGS_DIMENSION)
            
            self.faiss_index.add(query_embedding.reshape(1, -1))
            
            # Add to memory cache
            cached = CachedAnswer(
                query_id=cache_id,
                query_text=query,
                query_embedding=query_embedding,
                answer=answer,
                context_tokens_used=context_tokens_used,
                model_used=model_used,
                pruning_ratio=pruning_ratio,
                source_pages=source_pages,
                created_at=""
            )
            self.cached_queries[cache_id] = cached
            self.query_order.append(cache_id)
            
            logger.info(f"✅ Cached query {cache_id}. Cache size: {len(self.cached_queries)}")
            
            return cache_id
            
        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return -1
    
    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache metrics
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_queries,
                    SUM(CASE WHEN accessed_count > 0 THEN 1 ELSE 0 END) as cache_hits,
                    SUM(context_tokens_used) as total_tokens_saved,
                    AVG(pruning_ratio) as avg_pruning_ratio,
                    MAX(created_at) as latest_query
                FROM query_cache
            """)
            
            row = cursor.fetchone()
            
            total_queries = row[0] or 0
            cache_hits = row[1] or 0
            tokens_saved = row[2] or 0
            avg_ratio = row[3] or 0.0
            
            cache_hit_rate = cache_hits / total_queries if total_queries > 0 else 0.0
            
            # Estimate cost savings (based on Haiku pricing)
            baseline_cost = (tokens_saved / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M
            
            return {
                "total_queries": total_queries,
                "cache_hits": cache_hits,
                "cache_hit_rate": cache_hit_rate,
                "total_tokens_saved": tokens_saved,
                "avg_pruning_ratio": avg_ratio,
                "cost_saved_usd": baseline_cost,
                "cache_size_queries": len(self.cached_queries)
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}
    
    def clear_cache(self, older_than_hours: Optional[int] = None) -> int:
        """
        Clear cache entries, optionally by age.
        
        Args:
            older_than_hours: Delete entries older than N hours (None = clear all)
            
        Returns:
            Number of entries deleted
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if older_than_hours:
                cursor.execute(f"""
                    DELETE FROM query_cache
                    WHERE created_at < datetime('now', '-{older_than_hours} hours')
                """)
            else:
                cursor.execute("DELETE FROM query_cache")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='query_cache'")
            
            conn.commit()
            deleted_count = cursor.rowcount
            
            # Reset in-memory cache
            self.cached_queries.clear()
            self.query_order.clear()
            self.faiss_index = faiss.IndexFlatIP(settings.EMBEDDINGS_DIMENSION)
            
            logger.info(f"✅ Cleared {deleted_count} cache entries")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0


# Global cache instance
_cache: Optional[SemanticCache] = None


def get_cache() -> SemanticCache:
    """Get or create global cache instance."""
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


from dataclasses import dataclass  # Import at end to avoid circular dependency
