"""
Embedder Module

Generates and manages embeddings using sentence-transformers (all-MiniLM-L6-v2).
Local, CPU-efficient model - no GPU required.
"""

from typing import List, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from backend.config import settings
import logging

logger = logging.getLogger(__name__)


class Embedder:
    """Manages text embeddings using local SentenceTransformer model."""
    
    # Model is cached globally to avoid reloading
    _model: Optional[SentenceTransformer] = None
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedder with a SentenceTransformer model.
        
        Args:
            model_name: HuggingFace model ID (default: all-MiniLM-L6-v2)
                       - 384-dimensional embeddings
                       - ~22MB model size
                       - ~5ms encoding time per query
        """
        self.model_name = model_name
        self._load_model()
    
    def _load_model(self) -> None:
        """Load model from cache or download if first use."""
        if Embedder._model is None:
            logger.info(f"Loading SentenceTransformer model: {self.model_name}")
            Embedder._model = SentenceTransformer(self.model_name)
            logger.info(f"✅ Model loaded. Output dimension: {self.model_name}")
    
    def embed_chunks(self, chunks: List[str], show_progress: bool = True) -> np.ndarray:
        """
        Embed a list of text chunks using batch processing.
        
        Args:
            chunks: List of text strings
            show_progress: Show tqdm progress bar
            
        Returns:
            NumPy array of shape (n_chunks, 384) with float32 embeddings
        """
        if not chunks:
            return np.array([], dtype=np.float32).reshape(0, settings.EMBEDDINGS_DIMENSION)
        
        logger.info(f"Embedding {len(chunks)} chunks with {self.model_name}")
        
        # Batch encode with progress bar
        embeddings = Embedder._model.encode(
            chunks,
            batch_size=32,
            convert_to_numpy=True,
            show_progress_bar=show_progress
        )
        
        # Ensure float32 for compatibility with FAISS
        embeddings = embeddings.astype(np.float32)
        
        logger.info(f"✅ Embedded {len(chunks)} chunks. Shape: {embeddings.shape}")
        
        return embeddings
    
    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query string.
        
        Args:
            query: Query text
            
        Returns:
            NumPy array of shape (1, 384) with float32 embedding
        """
        embedding = Embedder._model.encode(
            query,
            convert_to_numpy=True
        )
        
        # Ensure float32
        embedding = embedding.astype(np.float32)
        
        return embedding
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
        """
        Embed multiple texts and return as list of arrays.
        Useful when you want individual embeddings, not a batch array.
        
        Args:
            texts: List of text strings
            batch_size: Batch size for encoding
            
        Returns:
            List of float32 NumPy arrays
        """
        embeddings = self.embed_chunks(texts, show_progress=False)
        return [embedding for embedding in embeddings]
    
    def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding (1D or 2D array)
            embedding2: Second embedding (1D or 2D array)
            
        Returns:
            Cosine similarity score (0-1)
        """
        # Normalize to unit vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        embedding1 = embedding1 / norm1
        embedding2 = embedding2 / norm2
        
        # Dot product gives cosine similarity for normalized vectors
        similarity = np.dot(embedding1, embedding2)
        
        # Clamp to [0, 1] (numerical errors might go slightly outside)
        return float(max(0.0, min(1.0, similarity)))
    
    def normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """
        L2-normalize embeddings for use with inner-product search (cosine similarity).
        
        FAISS IndexFlatIP with normalized vectors gives cosine similarity.
        
        Args:
            embeddings: Array of shape (n, 384)
            
        Returns:
            L2-normalized embeddings
        """
        # Compute L2 norm for each embedding
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # Avoid division by zero
        norms[norms == 0] = 1.0
        
        # Normalize
        normalized = embeddings / norms
        
        return normalized.astype(np.float32)
    
    @classmethod
    def get_model_info(cls) -> dict:
        """
        Get information about the loaded model.
        
        Returns:
            Dict with model info
        """
        if cls._model is None:
            return {"status": "not_loaded"}
        
        return {
            "model_name": cls._model.get_sentence_embedding_dimension(),
            "embedding_dimension": cls._model.get_sentence_embedding_dimension(),
            "max_seq_length": cls._model.get_max_seq_length()
        }
