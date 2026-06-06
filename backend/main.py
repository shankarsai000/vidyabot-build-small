"""
VidyaBot FastAPI Application

Main entry point for the backend API.
Initializes database, loads cache, sets up routes, and runs Uvicorn.
"""

import sys
import warnings

# Enforce UTF-8 encoding on standard streams to prevent Windows console encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Suppress Gradio's warning about Blocks parameters theme/css moving to launch()
warnings.filterwarnings("ignore", category=UserWarning, module="gradio")

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import init_db, close_db
from backend.cache.semantic_cache import get_cache
from backend.api.routes_ingest import router as ingest_router
from backend.api.routes_query import router as query_router
from backend.api.routes_stats import router as stats_router
from backend.routes_benchmark import router as benchmark_router
from backend.routes_interfaces import router as interfaces_router
from backend.routes_teacher import router as teacher_router


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========== Lifespan Events ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.
    
    Startup:
    - Initialize database
    - Load semantic cache
    - Validate API key
    
    Shutdown:
    - Close database connections
    """
    logger.info("🚀 VidyaBot starting up...")
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        init_db()
        logger.info("✅ Database initialized")
        
        # Validate LLM backend
        if settings.LLM_BACKEND == "ollama":
            logger.info("Checking Ollama connection...")
            from backend.llm.ollama_client import OllamaClient
            ollama_client = OllamaClient()
            if ollama_client.validate_connection():
                logger.info("✅ Ollama connected")
            else:
                logger.warning("⚠️  Ollama not reachable — start with: ollama serve")
        else:
            logger.info("Validating Anthropic API key...")
            from backend.llm.claude_client import ClaudeClient
            if not ClaudeClient.validate_api_key():
                logger.warning("⚠️  API key validation failed — some features may not work")
            else:
                logger.info("✅ API key validated")
        
        # Load semantic cache
        logger.info("Loading semantic cache...")
        cache = get_cache()
        cache.load_cache()
        logger.info("✅ Cache loaded")
        
        # Warmup cross-encoder reranker (v2 upgrade)
        logger.info("Warming up cross-encoder reranker...")
        try:
            from backend.retrieval.reranker import get_reranker
            reranker = get_reranker()
            reranker.warmup()
            logger.info("✅ Cross-encoder reranker warmed up")
        except Exception as e:
            logger.warning(f"⚠️  Could not warmup reranker: {e}")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    
    logger.info("✅ VidyaBot ready to serve")
    yield
    
    # Shutdown
    logger.info("🛑 VidyaBot shutting down...")
    try:
        close_db()
        logger.info("✅ Database closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# ========== FastAPI App Creation ==========
app = FastAPI(
    title="VidyaBot API",
    description="Offline-first AI tutor for Indian students - Context-pruned, cost-optimized",
    version="1.0.0",
    lifespan=lifespan
)


# ========== CORS Middleware ==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Include Routers ==========
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(stats_router)
app.include_router(benchmark_router)
app.include_router(interfaces_router)
app.include_router(teacher_router)

logger.info("✅ All routers registered")


# ========== Root Endpoint ==========
@app.get("/api")
async def api_root():
    """API information and documentation."""
    return {
        "name": "VidyaBot API",
        "version": "1.0.0",
        "endpoints": {
            "ingest": "POST /api/ingest - Upload PDF",
            "textbooks": "GET /api/textbooks - List textbooks",
            "query": "POST /api/query - Ask a question",
            "stats": "GET /api/stats - Get usage statistics",
            "health": "GET /api/health - Health check"
        },
        "documentation": "/docs"
    }


# ========== Mount Frontend ==========
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
    logger.info(f"Mounted frontend from {frontend_path}")
else:
    logger.warning(f"Frontend directory not found: {frontend_path}")


# ========== Error Handlers ==========
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return {
        "status": "error",
        "message": "An error occurred processing your request",
        "detail": str(exc)
    }


# ========== Main Entry Point ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting Uvicorn server on {settings.API_HOST}:{settings.API_PORT}")
    
    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,  # Set to True for development
        log_level="info"
    )
