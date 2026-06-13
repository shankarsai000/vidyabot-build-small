"""
VidyaBot Gradio UI — Offline AI Tutoring for Indian Students

Build Small 2026 Hackathon Entry
Custom Gradio interface with Indian flag theming, streaming responses,
and integrated metrics dashboard.
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

import gradio as gr
import logging
import time
from typing import Dict, Optional, Tuple

from backend.config import settings
from backend.database import get_db_connection, init_db
from backend.retrieval.context_pruner import ContextPruner
from backend.llm.prompt_builder import PromptBuilder
from backend.cache.semantic_cache import get_cache

logger = logging.getLogger(__name__)

# ========== Indian Flag Theme Colors ==========
SAFFRON = "#FF9933"
WHITE = "#FFFFFF"
GREEN = "#138808"
NAVY = "#000080"
DARK_BG = "#0f1117"
CARD_BG = "#1a1b26"
CARD_BORDER = "#2a2b3d"
TEXT_PRIMARY = "#e1e2e8"
TEXT_SECONDARY = "#9ca0b0"
ACCENT_GLOW = "rgba(255, 153, 51, 0.15)"


# ========== Custom CSS ==========
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

/* ===== Global Reset ===== */
.gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: #0f1117 !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* ===== Header ===== */
.vidya-header {
    text-align: center;
    padding: 2rem 1rem 1.5rem;
    background: linear-gradient(135deg, rgba(255,153,51,0.08) 0%, rgba(19,136,8,0.08) 100%);
    border-radius: 16px;
    border: 1px solid rgba(255,153,51,0.15);
    margin-bottom: 1.5rem;
}

.vidya-header h1 {
    font-family: 'Poppins', sans-serif !important;
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    background: linear-gradient(135deg, #FF9933, #FFFFFF 50%, #138808);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 !important;
    line-height: 1.3 !important;
}

.vidya-header p {
    color: #9ca0b0 !important;
    font-size: 1rem !important;
    margin: 0.5rem 0 0 !important;
    font-weight: 300;
}

/* ===== Indian Flag Accent Bar ===== */
.flag-bar {
    height: 4px;
    background: linear-gradient(90deg, #FF9933 33%, #FFFFFF 33%, #FFFFFF 66%, #138808 66%);
    border-radius: 2px;
    margin: 1rem 0;
}

/* ===== Tab Styling ===== */
.tabs {
    border: none !important;
}

button.selected {
    background: linear-gradient(135deg, rgba(255,153,51,0.2), rgba(19,136,8,0.15)) !important;
    border-bottom: 3px solid #FF9933 !important;
    color: #FF9933 !important;
    font-weight: 600 !important;
}

/* ===== Card Styling ===== */
.gr-panel, .gr-box, .gr-form {
    background: #1a1b26 !important;
    border: 1px solid #2a2b3d !important;
    border-radius: 12px !important;
}

/* ===== Primary Button ===== */
.primary-btn, button.primary {
    background: linear-gradient(135deg, #FF9933, #e68a2e) !important;
    color: #000 !important;
    font-weight: 600 !important;
    font-family: 'Poppins', sans-serif !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 12px 28px !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(255, 153, 51, 0.25) !important;
}

.primary-btn:hover, button.primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(255, 153, 51, 0.4) !important;
}

/* ===== Metrics Badge ===== */
.metrics-badge {
    background: linear-gradient(135deg, rgba(19,136,8,0.15), rgba(255,153,51,0.1)) !important;
    border: 1px solid rgba(19,136,8,0.3) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    backdrop-filter: blur(10px);
}

/* ===== Answer Box ===== */
.answer-box textarea {
    font-size: 1.05rem !important;
    line-height: 1.7 !important;
    color: #e1e2e8 !important;
    background: #1a1b26 !important;
}

/* ===== Dropdown Styling ===== */
.gr-dropdown {
    border-radius: 10px !important;
}

/* ===== Accordion ===== */
.gr-accordion {
    border: 1px solid #2a2b3d !important;
    border-radius: 12px !important;
    overflow: hidden;
}

/* ===== Stats Cards ===== */
.stat-card {
    background: linear-gradient(135deg, #1a1b26, #1e1f2e) !important;
    border: 1px solid #2a2b3d !important;
    border-radius: 14px !important;
    padding: 20px !important;
    text-align: center;
    transition: all 0.3s ease;
}

.stat-card:hover {
    border-color: rgba(255, 153, 51, 0.4) !important;
    transform: translateY(-3px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.3);
}

/* ===== Animations ===== */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.gr-panel {
    animation: fadeIn 0.4s ease-out;
}

@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 5px rgba(255,153,51,0.2); }
    50% { box-shadow: 0 0 20px rgba(255,153,51,0.4); }
}

/* ===== Scrollbar ===== */
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-track {
    background: #0f1117;
}
::-webkit-scrollbar-thumb {
    background: #2a2b3d;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #FF9933;
}

/* ===== Mobile Responsive ===== */
@media (max-width: 768px) {
    .vidya-header h1 {
        font-size: 1.6rem !important;
    }
    .gradio-container {
        padding: 8px !important;
    }
}
"""


# ========== Helper Functions ==========

def get_textbook_choices() -> list:
    """Fetch available textbooks from database for dropdown."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, subject, grade FROM textbooks
            ORDER BY ingested_at DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            return []
        return [(f"{row[1]} ({row[2]}, Grade {row[3]})", row[0]) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching textbooks: {e}")
        return []


def get_llm_client():
    """Factory: returns OllamaClient or ClaudeClient based on config."""
    if settings.LLM_BACKEND == "ollama":
        from backend.llm.ollama_client import OllamaClient
        return OllamaClient()
    else:
        from backend.llm.claude_client import ClaudeClient
        return ClaudeClient()


def translate_text(text: str, target_lang: str, source_lang: str = "english") -> Optional[str]:
    """Translate text using deep-translator (graceful degradation)."""
    if target_lang == source_lang:
        return text
    try:
        from deep_translator import GoogleTranslator
        lang_map = {
            "hindi": "hi", "kannada": "kn", "telugu": "te",
            "tamil": "ta", "marathi": "mr", "bengali": "bn", "english": "en"
        }
        source_code = lang_map.get(source_lang, "en")
        target_code = lang_map.get(target_lang, "en")
        translator = GoogleTranslator(source_language=source_code, target_language=target_code)
        return translator.translate(text)
    except Exception as e:
        logger.warning(f"Translation failed ({source_lang} → {target_lang}): {e}")
        return None


# ========== Core Query Function ==========

def process_query(question: str, textbook_choice, language: str, mode: str):
    """
    Process a student question through the full pipeline.
    
    Returns: (answer, metrics_md, source_md, debug_json)
    """
    if not question or not question.strip():
        yield ("❌ Please enter a question.", "", "", {})
        return
    
    if not textbook_choice:
        yield ("❌ Please select a textbook first. Upload one in the 'Upload Textbook' tab.", "", "", {})
        return
    
    # Extract textbook_id from choice
    textbook_id = textbook_choice
    
    start_time = time.time()
    
    # Map display language to internal key
    lang_map = {
        "English": "english",
        "हिंदी (Hindi)": "hindi",
        "ಕನ್ನಡ (Kannada)": "kannada",
        "తెలుగు (Telugu)": "telugu",
        "தமிழ் (Tamil)": "tamil",
    }
    language_key = lang_map.get(language, "english")
    
    # Translate question if needed
    query_text = question
    translation_note = ""
    if language_key != "english":
        translated = translate_text(question, "english", language_key)
        if translated:
            query_text = translated
        else:
            translation_note = f"*[Answering in English — {language} translation unavailable]*\n\n"
    
    # Show "thinking" state
    yield ("🔍 Searching your textbook...", "", "", {})
    
    # Check semantic cache
    cache = get_cache()
    cached_result = cache.check_cache(query_text, textbook_id)
    
    if cached_result:
        elapsed_ms = (time.time() - start_time) * 1000
        answer = cached_result["answer"]
        
        if language_key != "english":
            translated_answer = translate_text(answer, language_key, "english")
            if translated_answer:
                answer = translated_answer
        
        if translation_note:
            answer = translation_note + answer
        
        metrics_md = _format_metrics(
            tokens_used=0,
            tokens_saved=settings.BASELINE_TOKENS,
            cost_usd=0.0,
            time_ms=elapsed_ms,
            cache_hit=True,
            pruning_ratio=cached_result.get("pruning_ratio", 0.0)
        )
        
        source_md = f"📄 Source: {cached_result.get('source_pages', 'cached')}"
        
        yield (answer, metrics_md, source_md, {"type": "cache_hit", "similarity": cached_result.get("similarity", 0.0)})
        return
    
    # Context Pruning
    yield ("🧠 Running context pruning pipeline...", "", "", {})
    
    try:
        pruner = ContextPruner()
        pruning_result = pruner.prune(query_text, textbook_id)
    except Exception as e:
        logger.error(f"Pruning error: {e}")
        yield (f"❌ Error searching textbook: {str(e)}", "", "", {})
        return
    
    # Build Prompts
    prompt_builder = PromptBuilder(grade=8, language=language_key)
    system_prompt = prompt_builder.build_system_prompt()
    
    if mode == "Socratic":
        user_prompt = prompt_builder.build_socratic_prompt(query_text, pruning_result.chunks)
    elif mode == "Quiz":
        user_prompt = prompt_builder.build_quiz_prompt(pruning_result.chunks)
    else:
        user_prompt = prompt_builder.build_user_prompt(query_text, pruning_result.chunks)
    
    # Source pages
    source_pages = ", ".join(
        str(c.page_number) for c in pruning_result.chunks if c.page_number
    )
    
    # Call LLM with streaming
    yield ("💬 Generating answer...", "", "", {})
    
    try:
        llm_client = get_llm_client()
        
        # Check if we can stream (Ollama supports it)
        if hasattr(llm_client, 'generate_stream') and settings.LLM_BACKEND == "ollama":
            # Streaming mode
            full_answer = ""
            for token in llm_client.generate_stream(system_prompt, user_prompt, max_tokens=256):
                full_answer += token
                elapsed_ms = (time.time() - start_time) * 1000
                metrics_md = _format_metrics(
                    tokens_used=llm_client.estimate_tokens(full_answer),
                    tokens_saved=pruning_result.tokens_saved,
                    cost_usd=0.0,
                    time_ms=elapsed_ms,
                    cache_hit=False,
                    pruning_ratio=pruning_result.pruning_ratio
                )
                source_md = f"📄 **Source pages:** {source_pages}" if source_pages else "📄 No specific page references"
                yield (
                    translation_note + full_answer,
                    metrics_md,
                    source_md,
                    {
                        "pruning_stages": pruning_result.stage_timings,
                        "chunks_used": len(pruning_result.chunks),
                        "tokens_after_pruning": pruning_result.total_tokens,
                        "model": settings.OLLAMA_MODEL
                    }
                )
            
            answer = full_answer
            # Estimate tokens for the final response
            input_tokens = llm_client.estimate_tokens(system_prompt + user_prompt)
            output_tokens = llm_client.estimate_tokens(answer)
            
        else:
            # Non-streaming mode (Claude or fallback)
            llm_response = llm_client.ask(system_prompt, user_prompt, max_tokens=256)
            answer = llm_response.answer
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        
        # Translate answer back if needed
        if language_key != "english":
            translated_answer = translate_text(answer, language_key, "english")
            if translated_answer:
                answer = translated_answer
        
        if translation_note:
            answer = translation_note + answer
        
        # Calculate costs
        if settings.LLM_BACKEND == "ollama":
            actual_cost = 0.0  # Local inference = free
        else:
            actual_cost = (
                (input_tokens / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M +
                (output_tokens / 1_000_000) * settings.HAIKU_OUTPUT_COST_PER_1M
            )
        
        baseline_cost = (settings.BASELINE_TOKENS / 1_000_000) * settings.HAIKU_INPUT_COST_PER_1M
        cost_saved = baseline_cost - actual_cost
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Log cost
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cost_log
                (baseline_tokens, actual_tokens_used, tokens_saved, cost_usd,
                 cost_saved_usd, cache_hit, model_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                settings.BASELINE_TOKENS,
                input_tokens + output_tokens,
                pruning_result.tokens_saved,
                actual_cost,
                cost_saved,
                False,
                settings.OLLAMA_MODEL if settings.LLM_BACKEND == "ollama" else settings.MODEL_NAME
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Cost logging failed: {e}")
        
        # Cache result
        try:
            cache.store_in_cache(
                query=query_text,
                answer=answer,
                context_tokens_used=input_tokens,
                textbook_id=textbook_id,
                model_used=settings.OLLAMA_MODEL if settings.LLM_BACKEND == "ollama" else settings.MODEL_NAME,
                pruning_ratio=pruning_result.pruning_ratio,
                source_pages=source_pages
            )
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")
        
        # Final output
        metrics_md = _format_metrics(
            tokens_used=input_tokens + output_tokens,
            tokens_saved=pruning_result.tokens_saved,
            cost_usd=actual_cost,
            time_ms=elapsed_ms,
            cache_hit=False,
            pruning_ratio=pruning_result.pruning_ratio
        )
        
        source_md = f"📄 **Source pages:** {source_pages}" if source_pages else "📄 No specific page references"
        
        debug_json = {
            "pruning_stages": pruning_result.stage_timings,
            "chunks_used": len(pruning_result.chunks),
            "tokens_after_pruning": pruning_result.total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": settings.OLLAMA_MODEL if settings.LLM_BACKEND == "ollama" else settings.MODEL_NAME,
            "total_time_ms": elapsed_ms
        }
        
        yield (answer, metrics_md, source_md, debug_json)
        
    except Exception as e:
        logger.error(f"LLM error: {e}", exc_info=True)
        yield (f"❌ Error generating answer: {str(e)}", "", "", {"error": str(e)})


def _format_metrics(tokens_used: int, tokens_saved: int, cost_usd: float,
                    time_ms: float, cache_hit: bool, pruning_ratio: float) -> str:
    """Format metrics as a beautiful Markdown badge."""
    savings_pct = pruning_ratio * 100
    
    cost_display = f"${cost_usd:.6f}" if cost_usd > 0 else "**$0.00** (local)"
    cache_badge = "✅ Cache Hit" if cache_hit else ""
    
    return f"""
### 📊 Query Metrics
| Metric | Value |
|--------|-------|
| ⚡ **Response Time** | {time_ms:.0f} ms |
| 🎯 **Tokens Used** | {tokens_used:,} |
| 💰 **Tokens Saved** | {tokens_saved:,} ({savings_pct:.0f}% reduction) |
| 💵 **Cost** | {cost_display} |
| 🔄 **Cache** | {cache_badge if cache_hit else "Miss"} |
| 🧠 **Model** | {settings.OLLAMA_MODEL if settings.LLM_BACKEND == "ollama" else settings.MODEL_NAME} |
"""


# ========== Upload Function ==========

def upload_textbook(file, board: str, subject: str, grade: str, title: str):
    """Upload and ingest a PDF textbook."""
    if file is None:
        return "❌ Please select a PDF file to upload."
    
    try:
        import tempfile
        import shutil
        from backend.ingestion.pdf_parser import PDFParser
        from backend.ingestion.chunker import Chunker
        from backend.ingestion.embedder import Embedder
        
        start_time = time.time()
        
        # Parse PDF
        parser = PDFParser(file.name)
        parsed_pages = parser.parse()
        pdf_metadata = parser.get_metadata()
        
        # Chunk text
        chunker = Chunker(
            max_chunk_tokens=settings.CHUNK_MAX_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS
        )
        chunks = chunker.chunk_by_section(parsed_pages)
        
        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        import os
        filename = os.path.basename(file.name)
        
        cursor.execute("""
            INSERT INTO textbooks
            (filename, title, board, subject, grade, total_pages, total_chunks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            filename,
            title or pdf_metadata.get("title", filename),
            board, subject, grade,
            len(parsed_pages), len(chunks)
        ))
        conn.commit()
        
        cursor.execute("SELECT last_insert_rowid()")
        textbook_id = cursor.fetchone()[0]
        
        # Insert chunks
        for chunk in chunks:
            chunk.textbook_id = textbook_id
            cursor.execute("""
                INSERT INTO chunks
                (textbook_id, chapter_number, chapter_title, section_title,
                 page_number, chunk_index, content, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.textbook_id, chunk.chapter_number,
                chunk.chapter_title, chunk.section_title,
                chunk.page_number, chunk.chunk_index,
                chunk.content, chunk.token_count
            ))
        conn.commit()
        
        # Add embeddings
        embedder = Embedder()
        texts = [chunk.content for chunk in chunks]
        embeddings = embedder.embed_chunks(texts, show_progress=True)
        
        for chunk, embedding in zip(chunks, embeddings):
            embedding_bytes = embedding.astype('float32').tobytes()
            cursor.execute("""
                UPDATE chunks SET embedding = ? WHERE textbook_id = ? AND chunk_index = ?
            """, (embedding_bytes, textbook_id, chunk.chunk_index))
        conn.commit()
        
        # Build indexes
        try:
            pruner = ContextPruner()
            pruner.setup_textbook(textbook_id)
        except Exception as e:
            logger.warning(f"Index building had issues: {e}")
        
        elapsed = time.time() - start_time
        
        return (
            f"✅ **Textbook uploaded successfully!**\n\n"
            f"| Detail | Value |\n"
            f"|--------|-------|\n"
            f"| 📚 Title | {title} |\n"
            f"| 📖 Pages | {len(parsed_pages)} |\n"
            f"| 🧩 Chunks | {len(chunks)} |\n"
            f"| ⏱️ Processing | {elapsed:.1f}s |\n"
            f"| 🆔 Textbook ID | {textbook_id} |\n\n"
            f"You can now ask questions about this textbook in the **Ask VidyaBot** tab!"
        )
        
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return f"❌ Upload failed: {str(e)}"


# ========== Dashboard Function ==========

def get_dashboard_stats():
    """Fetch and format dashboard statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_queries,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                SUM(tokens_saved) as total_tokens_saved,
                SUM(cost_saved_usd) as total_savings_usd,
                AVG(actual_tokens_used) as avg_tokens
            FROM cost_log
        """)
        row = cursor.fetchone()
        
        total_queries = row[0] or 0
        cache_hits = row[1] or 0
        tokens_saved = row[2] or 0
        total_savings = row[3] or 0.0
        avg_tokens = row[4] or 0
        
        cursor.execute("SELECT COUNT(*) FROM textbooks")
        textbooks_count = cursor.fetchone()[0]
        
        cache_rate = (cache_hits / total_queries * 100) if total_queries > 0 else 0
        
        stats_md = f"""
## 📊 VidyaBot Dashboard

### Usage Statistics
| Metric | Value |
|--------|-------|
| 📝 **Total Queries** | {total_queries:,} |
| 📚 **Textbooks Loaded** | {textbooks_count} |
| 🔄 **Cache Hit Rate** | {cache_rate:.1f}% |
| ⚡ **Avg Tokens/Query** | {avg_tokens:,.0f} |

### Cost Savings
| Metric | Value |
|--------|-------|
| 💰 **Total Tokens Saved** | {tokens_saved:,} |
| 💵 **Total Cost Saved** | ${total_savings:.6f} |
| 🧠 **LLM Backend** | {settings.LLM_BACKEND.upper()} ({settings.OLLAMA_MODEL if settings.LLM_BACKEND == "ollama" else settings.MODEL_NAME}) |
| 🌐 **Mode** | {"🔌 Offline (Local)" if settings.LLM_BACKEND == "ollama" else "☁️ Cloud"} |

### Merit Badges Earned
| Badge | Status |
|-------|--------|
| 🔌 **Off the Grid** | {"✅ Earned" if settings.LLM_BACKEND == "ollama" else "❌ Using cloud API"} |
| 🦙 **Llama Champion** | {"✅ Earned (llama.cpp via Ollama)" if settings.LLM_BACKEND == "ollama" else "❌"} |
| 🎨 **Off-Brand** | ✅ Custom Gradio UI |
"""
        return stats_md
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"❌ Error loading dashboard: {str(e)}"


# ========== Build Gradio Interface ==========

def create_demo() -> gr.Blocks:
    """Create the VidyaBot Gradio interface."""
    
    with gr.Blocks(
        title="VidyaBot — Offline AI Tutoring",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.Color(
                c50="#fff7ed", c100="#ffedd5", c200="#fed7aa",
                c300="#fdba74", c400="#fb923c", c500="#FF9933",
                c600="#ea580c", c700="#c2410c", c800="#9a3412",
                c900="#7c2d12", c950="#431407"
            ),
            secondary_hue="green",
            neutral_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
            font_mono=gr.themes.GoogleFont("JetBrains Mono"),
        ).set(
            body_background_fill="#0f1117",
            body_background_fill_dark="#0f1117",
            block_background_fill="#1a1b26",
            block_background_fill_dark="#1a1b26",
            block_border_color="#2a2b3d",
            block_border_color_dark="#2a2b3d",
            block_label_text_color="#9ca0b0",
            block_title_text_color="#e1e2e8",
            body_text_color="#e1e2e8",
            body_text_color_dark="#e1e2e8",
            button_primary_background_fill="#FF9933",
            button_primary_background_fill_hover="#e68a2e",
            button_primary_text_color="#000000",
            input_background_fill="#1e1f2e",
            input_background_fill_dark="#1e1f2e",
            input_border_color="#2a2b3d",
            input_border_color_dark="#2a2b3d",
        )
    ) as demo:
        
        # ===== Header =====
        gr.HTML("""
        <div class="vidya-header">
            <h1>📚 VidyaBot</h1>
            <p>Small models, big impact — offline AI tutoring for Indian students</p>
            <div class="flag-bar"></div>
            <p style="font-size: 0.85rem; color: #6b7280; margin-top: 0.5rem;">
                Build Small 2026 • Off the Grid 🔌 • Llama Champion 🦙
            </p>
        </div>
        """)
        
        with gr.Tabs() as tabs:
            
            # ===== TAB 1: Ask VidyaBot =====
            with gr.Tab("💬 Ask VidyaBot", id="ask"):
                with gr.Row():
                    with gr.Column(scale=1):
                        textbook_dropdown = gr.Dropdown(
                            choices=get_textbook_choices(),
                            label="📚 Select Textbook",
                            info="Choose the textbook to search in",
                            interactive=True,
                            elem_id="textbook-select"
                        )
                    with gr.Column(scale=1):
                        language_dropdown = gr.Dropdown(
                            choices=["English", "हिंदी (Hindi)", "ಕನ್ನಡ (Kannada)", "తెలుగు (Telugu)", "தமிழ் (Tamil)"],
                            value="English",
                            label="🌐 Language",
                            info="Get answers in your language",
                            interactive=True
                        )
                    with gr.Column(scale=1):
                        mode_dropdown = gr.Dropdown(
                            choices=["Answer", "Socratic", "Quiz"],
                            value="Answer",
                            label="🎯 Mode",
                            info="How would you like to learn?",
                            interactive=True
                        )
                
                question_input = gr.Textbox(
                    label="❓ Your Question",
                    placeholder="e.g., What is photosynthesis? / प्रकाश संश्लेषण क्या है?",
                    lines=3,
                    max_lines=5,
                    elem_id="question-input"
                )
                
                submit_btn = gr.Button(
                    "🚀 Ask VidyaBot",
                    variant="primary",
                    size="lg",
                    elem_id="submit-btn"
                )
                
                # Output area
                answer_output = gr.Textbox(
                    label="📝 Answer",
                    interactive=False,
                    lines=8,
                    max_lines=20,
                    elem_classes=["answer-box"],
                    elem_id="answer-output"
                )
                
                metrics_output = gr.Markdown(
                    label="📊 Metrics",
                    elem_classes=["metrics-badge"],
                    elem_id="metrics-output"
                )
                
                source_output = gr.Markdown(
                    label="📄 Sources",
                    elem_id="source-output"
                )
                
                with gr.Accordion("🔧 Debug Info (for developers)", open=False):
                    debug_output = gr.JSON(
                        label="Pipeline Debug",
                        elem_id="debug-output"
                    )
                
                # Wire up the submit action
                submit_btn.click(
                    fn=process_query,
                    inputs=[question_input, textbook_dropdown, language_dropdown, mode_dropdown],
                    outputs=[answer_output, metrics_output, source_output, debug_output],
                    queue=True
                )
                
                # Also trigger on Enter key
                question_input.submit(
                    fn=process_query,
                    inputs=[question_input, textbook_dropdown, language_dropdown, mode_dropdown],
                    outputs=[answer_output, metrics_output, source_output, debug_output],
                    queue=True
                )
            
            # ===== TAB 2: Upload Textbook =====
            with gr.Tab("📤 Upload Textbook", id="upload"):
                gr.Markdown("""
                ### Upload a PDF Textbook
                Upload your textbook to start asking questions about it.
                Supported: NCERT, CBSE, SSLC, Maharashtra Board textbooks.
                """)
                
                with gr.Row():
                    file_upload = gr.File(
                        label="📎 Select PDF",
                        file_types=[".pdf"],
                        type="filepath",
                        elem_id="file-upload"
                    )
                
                with gr.Row():
                    with gr.Column():
                        title_input = gr.Textbox(
                            label="📖 Textbook Title",
                            placeholder="e.g., Science Class 10"
                        )
                        board_input = gr.Dropdown(
                            choices=["NCERT", "CBSE", "SSLC", "Maharashtra", "Karnataka", "Other"],
                            label="🏫 Board",
                            value="NCERT"
                        )
                    with gr.Column():
                        subject_input = gr.Dropdown(
                            choices=["Science", "Mathematics", "Social Science", "English", "Hindi", "Other"],
                            label="📘 Subject",
                            value="Science"
                        )
                        grade_input = gr.Dropdown(
                            choices=["6", "7", "8", "9", "10", "11", "12"],
                            label="🎓 Grade",
                            value="10"
                        )
                
                upload_btn = gr.Button(
                    "📤 Upload & Index",
                    variant="primary",
                    size="lg"
                )
                
                upload_output = gr.Markdown(
                    label="Upload Status",
                    elem_id="upload-status"
                )
                
                def upload_and_refresh(file, board, subject, grade, title):
                    result = upload_textbook(file, board, subject, grade, title)
                    # Refresh the textbook dropdown
                    new_choices = get_textbook_choices()
                    return result, gr.update(choices=new_choices)
                
                upload_btn.click(
                    fn=upload_and_refresh,
                    inputs=[file_upload, board_input, subject_input, grade_input, title_input],
                    outputs=[upload_output, textbook_dropdown]
                )
            
            # ===== TAB 3: Dashboard =====
            with gr.Tab("📊 Dashboard", id="dashboard"):
                dashboard_output = gr.Markdown(elem_id="dashboard-content")
                
                refresh_btn = gr.Button("🔄 Refresh Stats", size="sm")
                refresh_btn.click(
                    fn=get_dashboard_stats,
                    outputs=[dashboard_output]
                )
                
                # Auto-load on tab select
                demo.load(
                    fn=get_dashboard_stats,
                    outputs=[dashboard_output]
                )
        
        # ===== Footer =====
        gr.HTML("""
        <div style="text-align: center; padding: 1.5rem; margin-top: 1rem; 
                    border-top: 1px solid #2a2b3d; color: #6b7280; font-size: 0.85rem;">
            <div class="flag-bar" style="height: 3px; margin-bottom: 1rem;
                 background: linear-gradient(90deg, #FF9933 33%, #FFFFFF 33%, #FFFFFF 66%, #138808 66%);
                 border-radius: 2px;"></div>
            <p>VidyaBot — Built with ❤️ for Indian students</p>
            <p style="font-size: 0.75rem; margin-top: 0.3rem;">
                Build Small 2026 Hackathon • Offline-First AI Tutoring • ≤32B Parameters
            </p>
        </div>
        """)
    
    demo.queue(max_size=20)
    return demo


# ========== Standalone Launch ==========
if __name__ == "__main__":
    init_db()
    demo = create_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_api=False
    )
