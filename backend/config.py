"""
VidyaBot Configuration Module

Loads all environment variables with python-dotenv.
Exports a Settings dataclass with all configuration constants.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class Settings:
    """Application settings loaded from environment variables."""
    
    # API Configuration
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001")
    
    # Token & Context Configuration
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "512"))
    TOKEN_BUDGET: int = int(os.getenv("MAX_CONTEXT_TOKENS", "512"))  # Alias
    BASELINE_TOKENS: int = 2000  # Baseline for cost comparison (full textbook)
    
    # Cache Configuration
    CACHE_SIMILARITY_THRESHOLD: float = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.90"))
    TOP_K_CHUNKS: int = int(os.getenv("TOP_K_CHUNKS", "3"))
    
    # Database Configuration
    DB_PATH: str = os.getenv("DB_PATH", "./data/vidyabot.db")
    
    # Embeddings Configuration
    EMBEDDINGS_MODEL: str = os.getenv("EMBEDDINGS_MODEL", "all-MiniLM-L6-v2")
    EMBEDDINGS_DIMENSION: int = 384  # all-MiniLM-L6-v2 output dimension
    
    # Retrieval Pipeline Configuration (3-Stage Pruning)
    BM25_TOP_K: int = 30  # Stage 1: BM25 keyword filter
    SEMANTIC_TOP_K: int = 10  # Stage 2: Semantic reranker
    FINAL_TOP_K: int = 3  # Stage 3: Final context window
    
    # LLM Cost Constants (Claude Haiku pricing per 1M tokens)
    HAIKU_INPUT_COST_PER_1M: float = 0.25  # $0.25 per 1M input tokens
    HAIKU_OUTPUT_COST_PER_1M: float = 1.25  # $1.25 per 1M output tokens
    
    # PDF Processing
    PDF_MAX_PAGES: int = 500  # Maximum pages per PDF
    CHUNK_MAX_TOKENS: int = 200  # Maximum tokens per chunk before splitting
    CHUNK_OVERLAP_TOKENS: int = 20  # Token overlap for sliding window
    
    # API Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Language Support
    SUPPORTED_LANGUAGES: list = field(default_factory=lambda: [
        "english",
        "hindi",
        "kannada",
        "telugu",
        "tamil",
        "marathi",
        "bengali"
    ])
    
    # ========== V2 UPGRADE SETTINGS ==========
    
    # Sentence-Level Pruning (Stage 4)
    SENTENCE_KEEP_THRESHOLD: float = 0.20  # Keep sentences with similarity >= 0.20 (elite aggressive pruning)
    SENTENCE_ALWAYS_KEEP_FIRST: bool = True  # Always keep first sentence
    
    # Cross-Encoder Reranker (Stage 2 replacement)
    CROSSENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    CROSSENCODER_TOP_K: int = 5  # Keep top-5 after cross-encoder reranking
    
    # Curriculum Router (Stage 0)
    CURRICULUM_FILTER_ENABLED: bool = True
    CURRICULUM_FALLBACK_THRESHOLD: float = 0.3  # If <30% chapters pass, use all
    
    # Teacher Dashboard
    TEACHER_PIN: str = os.getenv("TEACHER_PIN", "1234")  # Simple PIN for demo
    
    # Multi-Interface Settings
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    
    # Voice Settings
    VOICE_MODEL: str = "openai/whisper-tiny"  # CPU-only, 39MB
    VOICE_MAX_DURATION_SECONDS: int = 30
    
    @classmethod
    def validate(cls) -> "Settings":
        """Validate critical settings are set."""
        settings = cls()
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment or .env file")
        return settings


# Global settings instance
settings = Settings()
