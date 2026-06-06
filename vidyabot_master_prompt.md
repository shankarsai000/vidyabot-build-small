# 🎯 VidyaBot Gradio Edition: Master Prompt & Architecture

**Hackathon:** Build Small 2026 (June 5-15)  
**Track:** Backyard AI (Chapter One)  
**Constraint:** ≤32B parameters, Gradio UI, HF Space deployment  
**Goal:** Prove offline-first context-pruned AI tutoring on commodity hardware with real student validation

---

## PART 1: SYSTEM CONTEXT (For Any LLM Code Generation)

### Project Identity
```
Name: VidyaBot Gradio
Tagline: "Small models, big impact — offline AI tutoring for Indian students"
Problem: 200M Indian students need cost-effective, offline-first AI tutoring
Solution: Wrap existing VidyaBot backend (80% cost reduction via pruning) 
          in Gradio UI, optimize for ≤32B local inference (Ollama)
Target User: Rural students + small-town teachers (actual real-world testing)
Judge Criteria: 
  - Problem specific & real? ✅ (proven by Build in Public)
  - Person actually used it? ✅ (1-2 real students testing)
  - Honest fit with constraint? ✅ (13B model = runs on 8GB laptop)
  - Polish of Gradio app? ✅ (custom UI, language selector, demo video)
```

### Non-Negotiables (Don't Break These)
1. **Offline-first**: Ollama + llama.cpp (no cloud inference APIs)
2. **3-stage pruning**: BM25 → Semantic rerank → Token budget (proven to work)
3. **Real user testing**: Actual student must test & validate by June 12
4. **Gradio Space hosting**: Must be deployable as public HF Space
5. **Merit badges**: Off-the-Grid + Llama Champion mandatory, others bonus
6. **Demo video**: 60-90 seconds showing actual student using it
7. **Field Notes blog**: Lessons learned + technical decisions

---

## PART 2: TECH STACK (For This Hackathon)

### What STAYS (Don't Rewrite)
```python
# Core pipeline — proven & efficient
├── backend/retrieval/context_pruner.py    # 3-stage magic (REUSE)
├── backend/ingestion/embedder.py          # MiniLM (already local)
├── backend/retrieval/bm25_index.py        # BM25 filter (already works)
├── backend/llm/prompt_builder.py          # Prompt templates (ADAPT)
├── backend/database.py                    # SQLite schema (REUSE)
└── backend/cache/semantic_cache.py        # Query dedup (REUSE)
```

### What CHANGES (Optimize for Offline)
```python
# Replace cloud APIs with local inference
backend/llm/claude_client.py
  ❌ Remove: Anthropic API calls
  ✅ Add: Ollama local inference wrapper
    - Model: mistral-7b-instruct or llama2-13b-chat
    - Endpoint: http://localhost:11434/api/generate (Ollama default)
    - Max tokens: 256 (keep outputs concise for speed)

# Add Ollama orchestration
backend/llm/ollama_client.py (NEW)
  - Check if Ollama is running
  - Load model if not present (auto-download from registry)
  - Stream responses + handle timeouts
```

### What's NEW (Gradio + Space)
```python
# Gradio frontend (replaces vanilla HTML/CSS/JS)
frontend/gradio_app.py (NEW — MAIN ENTRY)
  ├── Class: VidyaBotUI(gr.Interface)
  ├── Input blocks:
  │   ├── Dropdown: Select textbook (cached list)
  │   ├── Textbox: Student question
  │   ├── Dropdown: Language (English/Hindi/Kannada/Telugu/Tamil)
  │   └── Button: Ask
  ├── Output blocks:
  │   ├── Textbox: Answer (streaming)
  │   ├── Markdown: Metrics (tokens saved, time, cost)
  │   ├── Info: Source pages + confidence
  │   └── JSON: Debug (pruning stages, model output)
  └── Custom theme: Indian flag colors (saffron/white/green)

# Space deployment
.github/workflows/deploy_hf_space.yml (NEW)
  - Auto-sync repo to HF Space on push
  - Ollama model pre-download in requirements.txt

space_requirements.txt (NEW)
  - ollama (local inference)
  - gradio >= 4.0
  - sentence-transformers (MiniLM)
  - rank-bm25
  - faiss-cpu
  - pdfplumber
```

### Full Stack for Submission
```
┌─────────────────────────────────────────────┐
│   GRADIO INTERFACE (gr.Interface)           │
│   - Q/A + Language selector                 │
│   - Streaming response                      │
│   - Metrics badge (savings displayed)       │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  PYTHON BACKEND (FastAPI)                   │
│  - Routes: /api/query, /api/textbooks       │
├─────────────────────────────────────────────┤
│  3-STAGE RETRIEVAL PIPELINE                 │
│  ├─ BM25 filter (top-30 chunks)             │
│  ├─ Semantic rerank (top-10 chunks)         │
│  └─ Token budget (top-3 chunks)             │
│  Result: 400 tokens (vs 2000 baseline)      │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  LOCAL LLM (Ollama)                         │
│  Model: Mistral 7B or Llama2 13B            │
│  Runtime: llama.cpp (optimized inference)   │
│  Speed: ~100 tokens/sec on CPU              │
│  Memory: 8-10GB (fits in 16GB laptop)       │
└─────────────────────────────────────────────┘
        ↓                    ↓
   ┌────────────┐      ┌──────────────┐
   │  SQLite DB │      │  FAISS Cache │
   │ (textbook) │      │ (semantic)   │
   └────────────┘      └──────────────┘
```

---

## PART 3: 2-WEEK BUILD SCHEDULE (With Milestones)

### WEEK 1: Core Integration + Local Inference

**Day 1 (Thu Jun 5-6)** — Setup + Model Swap
```
□ Clone existing VidyaBot repo
□ Set up Ollama locally
  - Download Mistral 7B: ollama pull mistral:latest
  - Test inference: curl http://localhost:11434/api/generate -d '...'
□ Create ollama_client.py wrapper
  - Test response streaming
  - Validate token counts
□ Audit existing backend — what stays, what changes
□ Commit: "feat: init Ollama integration"
```

**Day 2 (Fri Jun 7)** — Gradio UI Skeleton
```
□ Create frontend/gradio_app.py
  - Basic Q&A interface (no styling yet)
  - Textbook dropdown (hardcoded options)
  - Language selector
□ Connect to existing /api/query endpoint
□ Test end-to-end: Gradio → FastAPI → Ollama → Response
□ Capture response time metrics
□ Commit: "feat: Gradio skeleton + Ollama pipeline"
```

**Day 3 (Sat Jun 8)** — Real User Testing Setup
```
□ Prepare 3-5 test questions in English + Hindi
□ Email students from Build in Public network
  - "Can you test new version Mon/Tue?"
  - Prepare small textbook (Math or Science chapter)
□ Upload test textbook via Gradio UI (test /api/ingest)
□ Create testing rubric:
  - Question answering accuracy (1-5)
  - Speed (acceptable? <5 seconds)
  - UI clarity (easy to use? 1-5)
  - Language support (does Hindi work?)
□ Commit: "test: user testing prep + sample data"
```

**Day 4 (Sun Jun 9)** — Polish & Metrics Dashboard
```
□ Add savings badge to Gradio UI
  - Display: "Tokens saved: 1234 | Cost: $0.0001"
  - Show pruning ratio visually (80% saved!)
□ Add source attribution
  - Show which pages/chapters provided answer
  - Confidence score (BM25 rank)
□ Add debug JSON output (for Field Notes blog)
  - Stages: BM25 score, semantic score, final tokens
□ Test with actual students (first batch feedback)
□ Commit: "feat: metrics dashboard + source attribution"
```

**Day 5 (Mon Jun 10)** — Well-Tuned Badge (Fine-tuning)
```
□ Collect student Q&A from testing
□ Create fine-tuning dataset:
  - ~50-100 examples: (question, answer, textbook_context)
  - Format for Llama2: chat template
□ Fine-tune Mistral or Llama2 locally
  - Use MLX or llama-cpp-python
  - Validate on held-out test set
□ Deploy fine-tuned model to Ollama
□ Compare: base vs fine-tuned on test questions
□ Commit: "feat: fine-tuned model + Well-Tuned badge"
```

**Day 6 (Tue Jun 11)** — Off-Brand UI (Custom Styling)
```
□ Customize Gradio UI with gr.Server (custom HTML/CSS)
  - Indian flag theme: saffron/white/green + Indigo accent
  - Typography: Use Google Fonts (Poppins + Lora)
  - Add VidyaBot logo
  - Smooth transitions + animations
□ Add language switcher with flag icons
□ Mobile-responsive layout (Gradio handles, but test on phone)
□ Test accessibility (color contrast, keyboard navigation)
□ Commit: "feat: Off-Brand custom UI + Indian aesthetic"
```

**Day 7 (Wed Jun 12)** — Final User Validation + Demo Recording
```
□ Run final testing session with 2-3 students
  - Record screen + audio
  - Capture: student asking question → response → shown answer
  - Ask: "Would you use this? What would you change?"
□ Film 60-90 second demo video
  - Show Gradio interface loading
  - Ask question in English
  - Switch to Hindi, ask again
  - Highlight savings badge
  - End with student testimonial
□ Export video (MP4 1080p)
□ Commit: "test: final user validation + demo video"
```

---

