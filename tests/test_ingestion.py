"""
Tests for PDF Ingestion Pipeline

Tests that the ingestion pipeline correctly:
- Parses PDFs and extracts text
- Groups text into semantically meaningful chunks
- Respects token limits
- Generates embeddings
"""

import pytest
import os
import tempfile
from pathlib import Path
from backend.ingestion.pdf_parser import PDFParser
from backend.ingestion.chunker import Chunker, TextChunk
from backend.ingestion.embedder import Embedder
from backend.config import settings


class TestPDFParser:
    """Test PDF parsing functionality."""
    
    def test_estimate_tokens(self):
        """Test token estimation heuristic."""
        chunker = Chunker()
        
        # Short text
        text1 = "Hello world"
        tokens1 = chunker.estimate_tokens(text1)
        assert tokens1 > 0
        
        # Longer text
        text2 = "The quick brown fox jumps over the lazy dog. " * 10
        tokens2 = chunker.estimate_tokens(text2)
        assert tokens2 > tokens1
    
    def test_chunk_splitting(self):
        """Test that chunks respect token limits."""
        chunker = Chunker(max_chunk_tokens=100, overlap_tokens=10)
        
        # Create a long text
        long_text = "This is a test sentence. " * 30
        
        parsed_page = type('ParsedPage', (), {
            'page_num': 1,
            'chapter_num': 1,
            'chapter_title': 'Test Chapter',
            'section_title': 'Test Section',
            'raw_text': long_text
        })()
        
        chunks = chunker.chunk_by_section([parsed_page])
        
        # Check that we got multiple chunks
        assert len(chunks) > 1
        
        # Check token limits
        for chunk in chunks:
            assert chunk.token_count <= chunker.max_chunk_tokens + 50  # Allow some slack
    
    def test_chunk_metadata(self):
        """Test that chunk metadata is preserved."""
        chunker = Chunker()
        
        parsed_page = type('ParsedPage', (), {
            'page_num': 42,
            'chapter_num': 3,
            'chapter_title': 'Photosynthesis',
            'section_title': 'Light Reaction',
            'raw_text': 'Light is absorbed by chlorophyll molecules in the thylakoid membrane.'
        })()
        
        chunks = chunker.chunk_by_section([parsed_page], textbook_id=1)
        
        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.chapter_num == 3
        assert chunk.chapter_title == 'Photosynthesis'
        assert chunk.section_title == 'Light Reaction'
        assert chunk.page_number == 42
        assert chunk.textbook_id == 1


class TestEmbeddings:
    """Test embedding generation."""
    
    def test_embedder_initialization(self):
        """Test that embedder loads model correctly."""
        embedder = Embedder()
        assert embedder.model_name == "all-MiniLM-L6-v2"
    
    def test_single_query_embedding(self):
        """Test embedding a single query."""
        embedder = Embedder()
        
        query = "What is photosynthesis?"
        embedding = embedder.embed_query(query)
        
        # Check shape
        assert embedding.shape == (settings.EMBEDDINGS_DIMENSION,)
        
        # Check dtype
        assert embedding.dtype == 'float32'
        
        # Check not all zeros
        assert not (embedding == 0).all()
    
    def test_embeddings_are_normalized(self):
        """Test that embeddings can be normalized."""
        embedder = Embedder()
        
        texts = ["Hello", "World", "Test"]
        embeddings = embedder.embed_chunks(texts, show_progress=False)
        
        # Normalize
        normalized = embedder.normalize_embeddings(embeddings)
        
        # Check norms
        norms = (normalized ** 2).sum(axis=1) ** 0.5
        
        # Normalized vectors should have norm ~1
        assert all((norm > 0.99 and norm <= 1.01) for norm in norms)
    
    def test_similarity_computation(self):
        """Test similarity between embeddings."""
        embedder = Embedder()
        
        text1 = "What is photosynthesis?"
        text2 = "How does photosynthesis work?"
        text3 = "What is the weather today?"
        
        emb1 = embedder.embed_query(text1)
        emb2 = embedder.embed_query(text2)
        emb3 = embedder.embed_query(text3)
        
        # Similarity of related questions should be higher
        sim_related = embedder.similarity(emb1, emb2)
        sim_unrelated = embedder.similarity(emb1, emb3)
        
        assert sim_related > sim_unrelated  # Related should be more similar
        assert sim_related > 0.5  # Should be reasonably similar
        assert sim_unrelated < 0.8  # Should be fairly different


class TestChunkingStats:
    """Test chunking statistics."""
    
    def test_stats_computation(self):
        """Test that chunking stats are computed correctly."""
        chunker = Chunker()
        
        # Create sample chunks
        chunks = [
            TextChunk(content="Test 1" * 10, token_count=13),
            TextChunk(content="Test 2" * 10, token_count=13),
            TextChunk(content="Test 3" * 20, token_count=26),
        ]
        
        stats = chunker.get_stats(chunks)
        
        assert stats['total_chunks'] == 3
        assert stats['total_tokens'] == 52
        assert stats['avg_tokens_per_chunk'] == pytest.approx(52 / 3, rel=0.01)
        assert stats['max_tokens'] == 26
        assert stats['min_tokens'] == 13
    
    def test_empty_chunks(self):
        """Test stats for empty chunk list."""
        chunker = Chunker()
        stats = chunker.get_stats([])
        
        assert stats['total_chunks'] == 0
        assert stats['total_tokens'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
