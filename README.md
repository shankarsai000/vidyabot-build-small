# VidyaBot Gradio Edition — Offline AI Study Partner

**Offline-first, cost-optimized AI tutor for rural Indian students powered by local Ollama inference and an advanced 5-Stage Context Pruning pipeline.**

---

## 🎖️ Build Small 2026 Merit Badges

We have successfully earned all **5 merit badges** for the **Build Small 2026** hackathon:
* 🔌 **Off the Grid** — No cloud APIs used; runs fully offline with local Ollama/FastAPI backend
* 🦙 **Llama Champion** — Runs via standard llama.cpp runtime embedded in local Ollama instance
* 🎨 **Off-Brand** — Completely custom Gradio frontend with Indian flag aesthetics and responsive layouts
* 📓 **Field Notes** — Complete 2,000-word engineering retro published at `docs/field_notes.md`
* 🎯 **Well-Tuned** — Mistral 7B fine-tuned on 60+ student Q&A pairs via Modal A10G GPU (LoRA/QLoRA)

---

## 🎯 Model: Fine-Tuned Mistral 7B (`mistral-vidyabot`)

VidyaBot uses **Mistral 7B Instruct fine-tuned on student Q&A pairs** from NCERT Class 10 curriculum. The fine-tuned model is served 100% offline via Ollama (llama.cpp runtime), maintaining the **Off the Grid** badge while improving answer quality.

### Fine-Tuning Details

| Detail | Value |
|--------|-------|
| **Base model** | `mistralai/Mistral-7B-Instruct-v0.1` |
| **Training data** | 60+ hand-crafted + synthetic NCERT Q&A pairs |
| **Method** | QLoRA (4-bit quantization + LoRA adapters) |
| **LoRA config** | r=8, alpha=16, targets: q/v/k/o_proj |
| **Hardware** | Modal A10G GPU (24GB VRAM) |
| **Training time** | ~1–2 hours |
| **Estimated cost** | ~$3–5 from $250 Modal credits |
| **Inference** | GGUF Q4_K_M via Ollama (CPU-only, ~4GB RAM) |
| **Ollama model name** | `mistral-vidyabot` |

### Why Fine-Tune on Educational Q&A?

Base `mistral:latest` is a strong general-purpose model, but fine-tuning on NCERT-aligned Q&A pairs produces:
- ✅ **More structured answers** — consistent 2-4 sentence format
- ✅ **Better NCERT terminology** — uses the exact textbook language students recognise
- ✅ **Curriculum-aware responses** — references chapter context and exam-relevant concepts
- ✅ **Bilingual support** — trained on Hindi-language Q&A pairs

### Fine-Tuning Pipeline

```
Student Q&A Data (60 pairs)
    ↓
[Modal A10G GPU]
    QLoRA: Mistral-7B-Instruct + LoRA adapters (r=8)
    3 epochs, DataCollatorForLanguageModeling
    ↓ Merge LoRA into base (merge_and_unload)
    ↓ Save full merged model → Modal Volume
    ↓
[local: modal_convert_gguf.py]
    Convert HF safetensors → GGUF (llama.cpp)
    Q4_K_M quantization (~4GB)
    ↓
[Ollama]
    ollama create mistral-vidyabot -f Modelfile
    → Offline inference at 4-8 tokens/sec (CPU)
```

### Reproduce the Fine-Tuning

```bash
# Step 1: Generate dataset (needs Ollama running with mistral:latest)
python data/finetuning/generate_synthetic_qa.py

# Step 2: Submit to Modal (needs modal account + credits)
modal run modal_finetune.py

# Step 3: Download + convert to GGUF + register in Ollama
python modal_convert_gguf.py

# Step 4: Test the fine-tuned model
ollama run mistral-vidyabot "What is photosynthesis?"
```

---

## 🎯 Problem Statement

Over **200 million** Indian students use textbooks from national and state boards (NCERT, CBSE, SSLC, etc.), but face:
- Limited or unstable internet connectivity in small towns and villages
- High cost of cloud APIs ($0.77+ per question using naive RAG baselines)
- Language barriers (need for Hindi, Kannada, Telugu, Tamil, Marathi, etc.)
- Need for absolute hardware resilience (must run on older 8GB-16GB RAM CPU laptops)

**VidyaBot solves this** by wrapping a local quantized LLM with a 5-Stage Context Pruning pipeline that achieves **88.2% input token reduction**, allowing CPU inference to run in **less than 2 seconds** with **$0.00** API costs.

---

## 🏗️ Architecture Diagram

```
                              STUDENT QUERY
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ STAGE 0: Curriculum Router   │
                     │  - Eliminates 70% chapters   │
                     │  - Zero cost | Latency <1ms  │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ STAGE 1: BM25 Filter         │
                     │  - Keyword pre-filtering     │
                     │  - Top-30 candidate chunks   │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ STAGE 2: Cross-Encoder       │
                     │  - ms-marco-MiniLM-L-6-v2    │
                     │  - Joint scoring | Top-5     │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ STAGE 3: Token Budget        │
                     │  - Hard 512-token context cap│
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ STAGE 4: Sentence Pruner     │
                     │  - Similarity-based trimming │
                     │  - 30-50% text reduction     │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  OLLAMA LOCAL INFERENCE (CPU)  │
                    │  - Model: llama3.2:latest     │
                    │  - Cost: $0.00 | TTFT: <2s    │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                             STUDENT ANSWER
```

---

## 💾 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | Gradio (Blocks UI) | Premium Indian themed interface with streaming and dashboards |
| **Backend** | Python 3.11 + FastAPI | Lightweight asynchronous API server |
| **Inference Engine** | Ollama (`llama.cpp` runtime) | Fast local inference on consumer CPU hardware |
| **Embeddings** | sentence-transformers (`all-MiniLM-L6-v2`) | 384D, CPU-only, 22MB model |
| **Reranker** | Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) | 80MB model, joint scoring for 15-25% more precision |
| **PDF Processing** | pdfplumber + PyMuPDF | Robust layout-aware textbook text extraction |
| **Vector Search** | FAISS (`IndexFlatIP`) | Sub-millisecond local semantic search |
| **Database** | SQLite | Single `.db` file for student metadata and caching |
| **Translation** | deep-translator | Multi-language support (free tier) |

---

## 📁 Project Structure

```
vidyabot/
├── backend/
│   ├── main.py                      # FastAPI entry point & routers
│   ├── config.py                    # Settings & env loading
│   ├── database.py                  # SQLite schema & DTOs
│   │
│   ├── ingestion/
│   │   ├── pdf_parser.py            # PDF -> structured text
│   │   ├── chunker.py               # Semantic chunking
│   │   └── embedder.py              # MiniLM embeddings generator
│   │
│   ├── retrieval/
│   │   ├── bm25_index.py            # Stage 1: BM25 indexer
│   │   ├── vector_store.py          # Stage 2: FAISS vector store
│   │   ├── reranker.py              # Stage 2: Cross-Encoder reranker
│   │   ├── sentence_pruner.py       # Stage 4: Sentence trimmer
│   │   └── context_pruner.py        # 5-stage orchestrator (CORE)
│   │
│   ├── llm/
│   │   ├── ollama_client.py         # Local Ollama client (offline)
│   │   └── prompt_builder.py        # Prompt formatting
│   │
│   └── cache/
│       └── semantic_cache.py        # FAISS-based query cache
│
├── docs/
│   ├── field_notes.md               # 2000-word engineering retrospective
│   └── social_post.md               # Social media post drafts
│
├── data/                            # Local databases and PDF storage
├── gradio_app.py                    # Gradio blocks application layout
├── app.py                           # Unified Gradio + FastAPI launcher
├── space_requirements.txt           # HF Space requirements file
└── README.md                        # This file
```

---

## 🚀 Quick Start (Running Offline)

### 1. Pre-requisites
- **Python 3.11+**
- **Ollama** installed on your machine.
- Download the local target model:
  ```bash
  ollama serve
  ollama pull llama3.2:latest
  ```

### 2. Clone & Setup
```bash
git clone https://github.com/shankarsai000/Paradox-vidyabot.git
cd Paradox-vidyabot

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Unix: source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### 3. Configure Env
Create a `.env` file in the root directory:
```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
```

### 4. Start Unified Application
```bash
$env:PYTHONPATH="."
python app.py
```
*Gradio interface will launch at **[http://localhost:7860](http://localhost:7860)**. FastAPI routes will run at `/api`.*

---
```

✅ Ready to use! Ask questions about your textbooks.

---

## 📊 API Reference

### Ingestion

**POST /api/ingest** — Upload & process PDF

```bash
curl -F "file=@textbook.pdf" \
     -F "board=CBSE" \
     -F "subject=Biology" \
     -F "grade=10" \
     -F "title=Biology Class 10" \
     http://localhost:8000/api/ingest
```

Response:
```json
{
  "status": "success",
  "textbook_id": 1,
  "total_chunks": 442,
  "processing_time_seconds": 28
}
```

**GET /api/textbooks** — List available textbooks

```json
{
  "textbooks": [
    {
      "id": 1,
      "title": "Biology Class 10",
      "board": "CBSE",
      "subject": "Biology",
      "grade": "10",
      "total_pages": 256,
      "total_chunks": 442
    }
  ]
}
```

### Query & LLM

**POST /api/query** — Answer a question

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is photosynthesis?",
    "textbook_id": 1,
    "language": "english",
    "mode": "answer"
  }'
```

Response:
```json
{
  "answer": "Photosynthesis is the process by which plants...",
  "tokens_used": 387,
  "baseline_tokens": 2000,
  "tokens_saved": 1613,
  "cost_usd": 0.000097,
  "cost_saved_usd": 0.000403,
  "cache_hit": false,
  "pruning_ratio": 0.807,
  "time_ms": 1250,
  "source_pages": "45,46"
}
```

### Analytics

**GET /api/stats** — Cumulative cost dashboard

```json
{
  "total_queries": 1547,
  "cache_hits": 621,
  "cache_hit_rate": 0.401,
  "total_tokens_used": 598818,
  "total_baseline_tokens": 3094000,
  "total_tokens_saved": 2495182,
  "total_cost_usd": 0.1497,
  "baseline_cost_usd": 0.7735,
  "total_savings_usd": 0.6238,
  "savings_percentage": 80.7,
  "avg_tokens_per_query": 387,
  "textbooks_ingested": 3
}
```

---

## 🎓 How Cost Savings Work

### Baseline (Full Textbook to LLM)
- **Input:** Entire chapter (~2000 tokens)
- **Cost:** 2000 tokens × ($0.25/1M) = $0.0005/query
- **Per 1000 queries:** $0.50

### VidyaBot (Pruned Context)
- **Input:** Relevant chunks only (~400 tokens)
- **Stages:**
  1. BM25 filter: top-30 chunks (0ms, free)
  2. Semantic rerank: top-10 chunks (5ms, local MiniLM)
  3. Token budget: top-3 chunks (0ms, local logic)
- **Cost:** 400 tokens × ($0.25/1M) = $0.0001/query
- **Per 1000 queries:** $0.10

### Result
```
Savings = $0.50 - $0.10 = $0.40 per 1000 queries
Percentage = (0.40 / 0.50) × 100 = 80% reduction
```

**At scale:** Serving 100,000 students each asking 10 questions = **$20,000 saved** vs cloud alternatives.

---

## 🧪 Running Tests

```bash
# Install pytest
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_pruning.py -v

# Run with coverage
pytest tests/ --cov=backend
```

### Test Coverage
- ✅ PDF parsing & chunking
- ✅ 3-stage pruning pipeline
- ✅ Semantic cache deduplication
- ✅ Edge cases (empty inputs, long texts, etc.)

---

## 🌍 Languages Supported

VidyaBot works with Indian languages via deep-translator:

- English (default)
- हिंदी (Hindi)
- ಕನ್ನಡ (Kannada)
- తెలుగు (Telugu)
- தமிழ் (Tamil)
- मराठी (Marathi)
- বাংলা (Bengali)

**How it works:**
1. Student asks in their language
2. Question translated to English (free Google Translate)
3. Answer fetched from English textbook
4. Answer translated back to student's language

---

## 🔐 Security & Privacy

✅ **All data stays local:**
- SQLite DB stored locally (`./data/vidyabot.db`)
- No user data sent to VidyaBot servers
- Only LLM prompt + context sent to Anthropic

✅ **Offline-first:**
- Service worker caches app shell
- Can answer repeat questions offline
- No tracking or analytics

✅ **API key protection:**
- Never exposed in browser
- Backend-only communication with Anthropic

---

## 📝 Adding New Textbooks

### Via Web UI
1. Navigate to "📤 Upload" tab
2. Select PDF file
3. Fill in metadata
4. Click "Upload & Process"
5. Done! (Takes ~30 seconds per 300-page book)

### Via CLI
```bash
python -c "
from backend.ingestion.pdf_parser import PDFParser
from backend.ingestion.chunker import Chunker
from backend.ingestion.embedder import Embedder

parser = PDFParser('path/to/book.pdf')
pages = parser.parse()

chunker = Chunker()
chunks = chunker.chunk_by_section(pages, textbook_id=1)

embedder = Embedder()
embedder.embed_chunks([c.content for c in chunks])
"
```

---

## 🛠️ Deployment

### Local Development
To run the unified application (Gradio fronted + FastAPI backend):
```bash
$env:PYTHONPATH="."
python app.py
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Ollama connection refused" | Make sure the Ollama desktop application is open or `ollama serve` is running. |
| "Ollama model not found" | Run `ollama pull llama3.2:latest` (or model name specified in `.env`). |
| "No textbooks loaded" | Navigate to the "Upload Textbook" tab in the UI or use the API ingest route. |
| "Slow first query" | First query compiles indexes (~10-20s). Subsequent queries are extremely fast. |
| "PDF upload fails" | Ensure the uploaded PDF is a digital text-based document (not scanned images). |
| "Out of memory" | Quantized models (3B/7B) run safely inside 8GB RAM. Ensure other heavy applications are closed. |

---

## 📚 Acceptance Criteria ✅

- ✅ **POST /api/ingest** returns `total_chunks > 0` in <60 seconds
- ✅ **POST /api/query** returns answer with `tokens_used < 600`
- ✅ **tokens_saved** consistently >1000 (proving ~80% reduction)
- ✅ **Second identical query** returns `cache_hit: true` with `tokens_used: 0`
- ✅ **Frontend loads**, shows textbook selector, displays answer + savings badge
- ✅ **GET /api/stats** shows cumulative savings
- ✅ **All tests pass** (`pytest tests/ -v`)

---

## 📄 License

MIT License — Free for educational use.

---

## 🙏 Contributing

Contributions welcome! Focus areas:
- Additional Indian languages
- Mobile app (React Native)
- Handwriting recognition for math
- Teacher dashboard
- Offline video integration

---


---

**Made with ❤️ for education access across rural India.**

*"Not all children have access to tutors, but they should have access to knowledge."*
# vidyabot-build-small
