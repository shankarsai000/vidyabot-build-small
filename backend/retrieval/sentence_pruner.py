"""
VidyaBot Sentence-Level Pruner — Stage 4 Surgical Token Removal

Given an already-retrieved chunk, remove sentences that don't help answer the query.
Expected: 30-50% token reduction from retrieved chunks.
Combined with chunk-level stages: 88-92% total reduction vs naive 2000-token RAG.

Algorithm:
1. Split chunk into sentences
2. Embed all sentences (batch) + query using existing MiniLM
3. Compute query-to-sentence similarity
4. Keep sentences with similarity >= THRESHOLD (0.30)
5. Always keep first sentence (topic sentence)
6. Reconstruct original order
"""

import re
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass
from backend.database import Chunk
from backend.ingestion.embedder import Embedder
from backend.config import settings


@dataclass
class SentencePruneResult:
    """Result of sentence-level pruning on a chunk."""
    original_text: str
    pruned_text: str
    original_tokens: int
    pruned_tokens: int
    sentences_kept: int
    sentences_removed: int
    reduction_pct: float  # Percentage reduction


class SentencePruner:
    """
    Surgically prune sentences from retrieved chunks to reduce token waste.
    
    Key insight: A 200-token chunk about "Photosynthesis" may contain:
    - 40 tokens: Topic sentence (photosynthesis is process converting light to energy)
    - 30 tokens: Relevant details (occurs in chloroplasts)
    - 50 tokens: Detailed mechanism (step-by-step CO2 + H2O → glucose)
    - 40 tokens: Tangential info (historical discovery, scientists who studied it)
    - 40 tokens: Related concepts (cellular respiration, ATP energy currency)
    
    Query: "What is the role of chloroplasts in photosynthesis?"
    Should keep: Topic + mechanism steps + chloroplast detail = ~110 tokens
    Should remove: Historical + tangential = ~80 tokens
    Result: 200 → 110 tokens (45% reduction)
    """
    
    # Similarity threshold: keep sentences > 0.30 similarity to query
    SENTENCE_KEEP_THRESHOLD = 0.30
    
    # Always preserve first sentence (usually topic sentence)
    ALWAYS_KEEP_FIRST = True
    
    def __init__(self, embedder: Optional[Embedder] = None):
        """Initialize with embedder (reuse existing instance if provided)."""
        self.embedder = embedder
    
    def _split_sentences(self, text: str) -> List[Tuple[str, int]]:
        """
        Split text into sentences preserving original index.
        
        Returns: List of (sentence_text, original_index) tuples
        """
        # Split on ". " or ".\n" or "! " or "?\n" or "?\s"
        # Use regex but keep track of original positions
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Filter empty sentences
        sent_with_idx = []
        for idx, sent in enumerate(sentences):
            if sent.strip():
                sent_with_idx.append((sent.strip(), idx))
        
        return sent_with_idx
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using simple heuristic: words * 1.3"""
        words = len(text.split())
        return max(1, int(words * 1.3))
    
    def prune_chunk(self, chunk: Chunk, query: str) -> SentencePruneResult:
        """
        Prune irrelevant sentences from a single chunk.
        
        Args:
            chunk: Chunk object with content
            query: User question to match against
        
        Returns:
            SentencePruneResult with pruning statistics
        """
        original_text = chunk.content
        original_tokens = self._estimate_tokens(original_text)
        
        # Split into sentences
        sentences = self._split_sentences(original_text)
        if not sentences:
            return SentencePruneResult(
                original_text=original_text,
                pruned_text="",
                original_tokens=original_tokens,
                pruned_tokens=0,
                sentences_kept=0,
                sentences_removed=0,
                reduction_pct=0.0
            )
        
        # Embed query + all sentences
        if not self.embedder:
            from backend.ingestion.embedder import Embedder
            self.embedder = Embedder()
        
        query_embedding = self.embedder.embed_query(query)  # shape (384,)
        sentences_text = [s[0] for s in sentences]
        sentence_embeddings = self.embedder.embed_chunks(sentences_text)  # shape (N, 384)
        
        # Compute cosine similarity: query vs each sentence
        # Both are normalized, so cosine sim = dot product
        similarities = np.dot(sentence_embeddings, query_embedding)  # shape (N,)
        
        # Determine which sentences to keep
        kept_indices = []
        for idx, (sent_text, orig_idx) in enumerate(sentences):
            similarity = similarities[idx]
            is_first = (orig_idx == 0)
            
            # Keep if: first sentence OR similarity above threshold
            if (self.ALWAYS_KEEP_FIRST and is_first) or (similarity >= self.SENTENCE_KEEP_THRESHOLD):
                kept_indices.append(idx)
        
        # Reconstruct pruned text in original order
        kept_sentence_objs = [(sentences[idx][0], sentences[idx][1]) for idx in kept_indices]
        kept_sentence_objs.sort(key=lambda x: x[1])  # Sort by original index
        pruned_sentences = [s[0] for s in kept_sentence_objs]
        pruned_text = " ".join(pruned_sentences)
        
        # Calculate stats
        pruned_tokens = self._estimate_tokens(pruned_text)
        sentences_kept = len(kept_indices)
        sentences_removed = len(sentences) - sentences_kept
        reduction_pct = ((original_tokens - pruned_tokens) / original_tokens * 100) if original_tokens > 0 else 0.0
        
        return SentencePruneResult(
            original_text=original_text,
            pruned_text=pruned_text,
            original_tokens=original_tokens,
            pruned_tokens=pruned_tokens,
            sentences_kept=sentences_kept,
            sentences_removed=sentences_removed,
            reduction_pct=reduction_pct
        )
    
    def prune_all_chunks(self, chunks: List[Chunk], query: str) -> Tuple[List[Chunk], dict]:
        """
        Prune all chunks for a query (batch operation).
        
        Args:
            chunks: List of Chunk objects to prune
            query: User question
        
        Returns:
            (pruned_chunks, statistics_dict)
            
        Pruned chunks have .content updated with sentence-pruned text.
        """
        if not chunks:
            return [], {}
        
        pruned_chunks = []
        total_tokens_removed = 0
        total_sentences_removed = 0
        
        for chunk in chunks:
            result = self.prune_chunk(chunk, query)
            
            # Update chunk with pruned content
            pruned_chunk = Chunk(
                id=chunk.id,
                textbook_id=chunk.textbook_id,
                chapter_number=chunk.chapter_number,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=result.pruned_text,  # ← Updated to pruned version
                token_count=result.pruned_tokens,
                embedding_bytes=chunk._embedding_bytes
            )
            pruned_chunks.append(pruned_chunk)
            
            total_tokens_removed += result.tokens_saved
            total_sentences_removed += result.sentences_removed
        
        # Statistics
        stats = {
            "chunks_processed": len(chunks),
            "total_original_tokens": sum(self._estimate_tokens(c.content) for c in chunks),
            "total_pruned_tokens": sum(self._estimate_tokens(c.content) for c in pruned_chunks),
            "total_tokens_removed": total_tokens_removed,
            "total_sentences_removed": total_sentences_removed,
            "avg_reduction_pct": sum(
                (self._estimate_tokens(chunks[i].content) - self._estimate_tokens(pruned_chunks[i].content)) / 
                max(1, self._estimate_tokens(chunks[i].content)) * 100
                for i in range(len(chunks))
            ) / len(chunks) if chunks else 0.0
        }
        
        return pruned_chunks, stats
    
    @property
    def tokens_saved(self) -> int:
        """Calculate tokens saved from last pruning operation (for logging)."""
        # This is calculated per-chunk in prune_chunk()
        return 0  # Tracked per-result


# Add property to SentencePruneResult
@property
def tokens_saved(self) -> int:
    """Tokens saved by pruning."""
    return self.original_tokens - self.pruned_tokens


SentencePruneResult.tokens_saved = tokens_saved


# Global pruner instance
_pruner: Optional[SentencePruner] = None


def get_pruner(embedder: Optional[Embedder] = None) -> SentencePruner:
    """Get singleton pruner instance."""
    global _pruner
    if _pruner is None:
        _pruner = SentencePruner(embedder=embedder)
    return _pruner
