"""
Query Routes

POST /api/query - Answer student question with context pruning and cost tracking
"""

import logging
import time
import hashlib
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db_connection
from backend.retrieval.context_pruner import ContextPruner
from backend.llm.prompt_builder import PromptBuilder
from backend.cache.semantic_cache import get_cache
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])

# Supported languages for translation
SUPPORTED_LANGUAGES = ["english", "hindi", "kannada", "telugu", "tamil", "marathi", "bengali"]


def get_llm_client():
    """Factory: returns OllamaClient or ClaudeClient based on config."""
    if settings.LLM_BACKEND == "ollama":
        from backend.llm.ollama_client import OllamaClient
        return OllamaClient()
    else:
        from backend.llm.claude_client import ClaudeClient
        return ClaudeClient()


def translate_text(text: str, target_lang: str, source_lang: str = "english") -> Optional[str]:
    """
    Translate text using deep-translator library.
    Returns None on failure (graceful degradation).
    """
    # Only skip translation if source and target are the same
    if target_lang == source_lang:
        return text
    
    try:
        from deep_translator import GoogleTranslator
        
        # Map language codes
        lang_map = {
            "hindi": "hi",
            "kannada": "kn",
            "telugu": "te",
            "tamil": "ta",
            "marathi": "mr",
            "bengali": "bn",
            "english": "en"
        }
        
        source_code = lang_map.get(source_lang, "en")
        target_code = lang_map.get(target_lang, "en")
        
        # Always attempt translation when source != target
        translator = GoogleTranslator(source_language=source_code, target_language=target_code)
        translated = translator.translate(text)
        logger.info(f"Successfully translated from {source_lang} to {target_lang}")
        return translated
    
    except Exception as e:
        logger.warning(f"Translation from {source_lang} to {target_lang} failed: {e}")
        return None


class QueryRequest(BaseModel):
    """Student query request model."""
    question: str
    textbook_id: int
    language: str = "english"
    mode: str = "answer"  # answer | socratic | quiz


class QueryResponse(BaseModel):
    """Query response model with detailed metrics."""
    answer: str
    language: str
    tokens_used: int
    baseline_tokens: int
    tokens_saved: int
    cost_usd: float
    cost_saved_usd: float
    cache_hit: bool
    pruning_ratio: float
    time_ms: float
    pruning_stages: Dict
    source_pages: str


@router.post("/query", response_model=QueryResponse)
async def answer_question(req: QueryRequest) -> QueryResponse:
    """
    Answer a student question using context pruning and Claude Haiku.
    
    Pipeline:
    1. If language != english, translate question to english
    2. Check semantic cache → if hit, return cached answer (0 tokens)
    3. Run 3-stage context pruner
    4. Build prompt within token budget
    5. Call Claude Haiku
    6. If language != english, translate answer back
    7. Log cost savings
    8. Cache result for future queries
    
    Args:
        req: QueryRequest with question, textbook_id, language, mode
        
    Returns:
        QueryResponse with answer and detailed metrics
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not req.question or len(req.question.strip()) == 0:
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        
        if req.textbook_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid textbook_id")
        
        logger.info(f"Query: {req.question[:50]} | Textbook: {req.textbook_id} | Lang: {req.language}")
        
        # Translate question if needed (graceful fallback if translation fails)
        query_text = req.question
        translation_note = ""
        
        if req.language != "english":
            translated = translate_text(req.question, "english", req.language)
            if translated:
                query_text = translated
                logger.info(f"Translated question from {req.language} to English")
            else:
                # Graceful degradation: answer in English with a note
                translation_note = f"[Note: Answering in English — {req.language} support coming soon]\n\n"
                logger.warning(f"Translation from {req.language} failed, proceeding with English question")
        
        # ========== STAGE 0: Check Semantic Cache ==========
        cache = get_cache()
        cached_result = cache.check_cache(query_text, req.textbook_id)
        
        if cached_result:
            # Cache hit - return immediately
            elapsed_ms = (time.time() - start_time) * 1000
            
            answer = cached_result["answer"]
            
            # Add translation note if applicable
            if translation_note and req.language != "english":
                answer = translation_note + answer
            
            # Attempt to translate back to original language if we have resources
            if req.language != "english":
                translated_answer = translate_text(answer, req.language, "english")
                if translated_answer:
                    answer = translated_answer
                    logger.info(f"Translated answer back to {req.language}")
                # If translation fails, return English answer with note
            
            return QueryResponse(
                answer=answer,
                language=req.language,
                tokens_used=0,
                baseline_tokens=settings.BASELINE_TOKENS,
                tokens_saved=settings.BASELINE_TOKENS,
                cost_usd=0.0,
                cost_saved_usd=cached_result.get("cost_saved_usd", 0.0),
                cache_hit=True,
                pruning_ratio=cached_result.get("pruning_ratio", 0.0),
                time_ms=elapsed_ms,
                pruning_stages={
                    "type": "cache_hit",
                    "cache_similarity": cached_result.get("similarity", 0.0)
                },
                source_pages=cached_result.get("source_pages", "")
            )
        
        # ========== STAGE 1-3: Context Pruning ==========
        pruner = ContextPruner()
        pruner_start = time.time()
        
        pruning_result = pruner.prune(query_text, req.textbook_id)
        
        pruning_ms = (time.time() - pruner_start) * 1000
        
        logger.info(
            f"Pruning: {len(pruning_result.chunks)} chunks, "
            f"{pruning_result.total_tokens} tokens "
            f"({pruning_result.pruning_ratio*100:.1f}% reduction)"
        )
        
        # ========== Build Prompts ==========
        prompt_builder = PromptBuilder(
            grade=8,  # Default grade - could extract from teacher profile
            language=req.language
        )
        
        system_prompt = prompt_builder.build_system_prompt()
        user_prompt = prompt_builder.build_user_prompt(
            query_text,
            pruning_result.chunks
        )
        
        # ========== Call LLM (Ollama or Claude) ==========
        llm_client = get_llm_client()
        llm_start = time.time()
        
        llm_response = llm_client.ask(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=256
        )
        
        llm_ms = (time.time() - llm_start) * 1000
        
        answer = llm_response.answer
        
        # Add translation note if query language was non-English
        if translation_note:
            answer = translation_note + answer
        
        # Translate answer back if needed (graceful fallback)
        if req.language != "english":
            translated_answer = translate_text(answer, req.language, "english")
            if translated_answer:
                answer = translated_answer
                logger.info(f"Translated answer to {req.language}")
            else:
                # Graceful degradation: return English answer with note
                logger.warning(f"Answer translation to {req.language} failed, returning English")
                # Already has translation_note prepended
        
        # ========== Log Cost & Save ==========
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate costs
        baseline_cost = (settings.BASELINE_TOKENS / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M
        actual_cost = llm_response.cost_usd
        cost_saved = baseline_cost - actual_cost
        
        # Extract source pages
        source_pages = ",".join(
            str(c.page_number) for c in pruning_result.chunks
            if c.page_number
        )
        
        # Log cost
        cursor.execute("""
            INSERT INTO cost_log
            (baseline_tokens, actual_tokens_used, tokens_saved, cost_usd,
             cost_saved_usd, cache_hit, model_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            settings.BASELINE_TOKENS,
            llm_response.input_tokens + llm_response.output_tokens,
            pruning_result.tokens_saved,
            actual_cost,
            cost_saved,
            False,
            llm_response.model
        ))
        conn.commit()
        
        logger.info(
            f"✅ Query complete. Cost: ${actual_cost:.6f}, "
            f"Saved: ${cost_saved:.6f} ({(cost_saved/baseline_cost)*100:.1f}%)"
        )
        
        # ========== Cache Result ==========
        cache.store_in_cache(
            query=query_text,
            answer=answer,
            context_tokens_used=llm_response.input_tokens,
            textbook_id=req.textbook_id,
            model_used=llm_response.model,
            pruning_ratio=pruning_result.pruning_ratio,
            source_pages=source_pages
        )
        
        # ========== Return Response ==========
        elapsed_ms = (time.time() - start_time) * 1000
        
        return QueryResponse(
            answer=answer,
            language=req.language,
            tokens_used=llm_response.input_tokens + llm_response.output_tokens,
            baseline_tokens=settings.BASELINE_TOKENS,
            tokens_saved=pruning_result.tokens_saved,
            cost_usd=actual_cost,
            cost_saved_usd=cost_saved,
            cache_hit=False,
            pruning_ratio=pruning_result.pruning_ratio,
            time_ms=elapsed_ms,
            pruning_stages={
                "bm25_candidates": settings.BM25_TOP_K,
                "semantic_candidates": settings.SEMANTIC_TOP_K,
                "final_chunks": len(pruning_result.chunks),
                "timings_ms": pruning_result.stage_timings
            },
            source_pages=source_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
