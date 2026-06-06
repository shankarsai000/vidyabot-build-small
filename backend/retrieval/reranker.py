"""
VidyaBot Cross-Encoder Reranker — Stage 2 Precision Reranking

Replaces bi-encoder similarity with more precise (query, chunk) joint scoring.
Bi-encoders encode independently; cross-encoders score together (15-25% more precise).

Trade-off: 5-10x slower than bi-encoder, but only runs on top-30 BM25 candidates.
Net result: Better chunks selected within same budget, reducing downstream token waste.
"""

from typing import List, Optional
import numpy as np
from dataclasses import dataclass
from backend.database import Chunk
from backend.config import settings


@dataclass
class RankedChunk:
    """Chunk with cross-encoder ranking score."""
    chunk: Chunk
    cross_encoder_score: float
    rank: int


class CrossEncoderReranker:
    """
    Uses cross-encoder/ms-marco-MiniLM-L-6-v2 to score (query, chunk) pairs jointly.
    
    Why cross-encoder beats bi-encoder:
    - Bi-encoder: embed(query) · embed(chunk) after separately encoding
    - Cross-encoder: score(query + chunk) end-to-end with attention across both
    
    Precision improvement: 15-25% higher on passage reranking benchmarks.
    Cost: ~5-10x slower than bi-encoder, but acceptable because:
    - Only runs on top-30 BM25 results (pre-filtered)
    - Latency: ~50-100ms for 30 passages on CPU
    - Prevents wrong chunks from wasting token budget downstream
    
    Model: cross-encoder/ms-marco-MiniLM-L-6-v2
    - 4.3M parameters, 80MB
    - CPU-optimized, no GPU needed
    - Trained on MS MARCO passage ranking (in-domain for our task)
    """
    
    MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(self):
        """Initialize reranker (lazy-load on first use)."""
        self._model = None
        self._warmup_done = False
    
    def _get_model(self):
        """Lazy-load model on first use."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                # This will download and cache the model (~80MB)
                self._model = CrossEncoder(self.MODEL_NAME, max_length=512)
                print(f"[Reranker] CrossEncoder loaded: {self.MODEL_NAME}")
            except ImportError:
                raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
        return self._model
    
    def warmup(self) -> None:
        """
        Pre-warm model on startup to avoid first-query latency spike.
        Makes a dummy prediction to load all weights into memory.
        """
        if self._warmup_done:
            return
        
        model = self._get_model()
        # Dummy warmup prediction
        dummy_query = "test question"
        dummy_text = "test answer"
        _ = model.predict([[dummy_query, dummy_text]])
        self._warmup_done = True
        print("[Reranker] CrossEncoder warmup complete")
    
    def rerank(self, query: str, candidate_chunks: List[Chunk], top_k: int = 5) -> List[RankedChunk]:
        """
        Score all (query, chunk) pairs and return top-k.
        
        Args:
            query: User question
            candidate_chunks: List of candidate Chunk objects (e.g., top-30 from BM25)
            top_k: Return only top-k chunks (default 5)
        
        Returns:
            List of RankedChunk objects sorted by cross_encoder_score descending
        """
        if not candidate_chunks:
            return []
        
        model = self._get_model()
        
        # Prepare (query, chunk_text) pairs
        pairs = []
        for chunk in candidate_chunks:
            pair = [query, chunk.content]
            pairs.append(pair)
        
        # Score all pairs in batch
        scores = model.predict(pairs)  # numpy array of shape (len(pairs),)
        
        # Create ranked chunks
        ranked = []
        for i, (chunk, score) in enumerate(zip(candidate_chunks, scores)):
            ranked.append(RankedChunk(
                chunk=chunk,
                cross_encoder_score=float(score),
                rank=i + 1
            ))
        
        # Sort by score descending and keep top_k
        ranked.sort(key=lambda x: x.cross_encoder_score, reverse=True)
        return ranked[:top_k]
    
    def batch_rerank(self, query: str, candidate_chunks_by_textbook: dict) -> dict:
        """
        Rerank candidates across multiple textbooks (for multi-corpus search).
        
        Args:
            query: User question
            candidate_chunks_by_textbook: {textbook_id: [list of chunks]}
        
        Returns:
            {textbook_id: [list of RankedChunk]}
        """
        results = {}
        for textbook_id, chunks in candidate_chunks_by_textbook.items():
            results[textbook_id] = self.rerank(query, chunks, top_k=5)
        return results


# Global reranker instance
_reranker: Optional[CrossEncoderReranker] = None


def get_reranker() -> CrossEncoderReranker:
    """Get singleton reranker instance."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker
