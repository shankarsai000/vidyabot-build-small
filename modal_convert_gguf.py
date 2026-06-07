"""
modal_convert_gguf.py — Download + Convert Fine-Tuned Model to GGUF

Run this AFTER modal_finetune.py completes.

Steps:
1. Download merged model from Modal Volume to local disk
2. Clone llama.cpp (for the conversion script)
3. Convert HuggingFace safetensors → GGUF (Q4_K_M quantization)
4. Place GGUF file where Ollama can read it

Usage (from project root, after fine-tuning completes):
    python modal_convert_gguf.py

Requirements:
    pip install modal
    pip install huggingface-hub
    Git + cmake available (for llama.cpp build)
"""

import subprocess
import sys
import os
from pathlib import Path


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
VOLUME_NAME = "vidyabot-model-output"
REMOTE_MODEL_PATH = "mistral-vidyabot-merged"
LOCAL_MODELS_DIR = Path("backend/llm/models")
LOCAL_HF_MODEL_DIR = LOCAL_MODELS_DIR / "mistral-vidyabot-hf"
LOCAL_GGUF_PATH = LOCAL_MODELS_DIR / "mistral-vidyabot.Q4_K_M.gguf"
LLAMACPP_DIR = LOCAL_MODELS_DIR / "llama.cpp"


def run(cmd: str, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command with live output."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        text=True, capture_output=False
    )
    if check and result.returncode != 0:
        print(f"  ❌ Command failed (exit {result.returncode})")
        sys.exit(1)
    return result


def step1_download_from_modal():
    """Download the merged HF model from Modal Volume to local disk."""
    print("\n[1/4] Downloading merged model from Modal Volume...")
    LOCAL_HF_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Use the Modal CLI to download
    cmd = (
        f"modal volume get {VOLUME_NAME} "
        f"{REMOTE_MODEL_PATH} {LOCAL_HF_MODEL_DIR}"
    )
    run(cmd)
    print(f"  ✅ Model downloaded to: {LOCAL_HF_MODEL_DIR}")


def step2_get_llamacpp():
    """Clone or update llama.cpp for the GGUF conversion script."""
    print("\n[2/4] Setting up llama.cpp conversion tools...")
    LOCAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if not LLAMACPP_DIR.exists():
        run(
            f"git clone --depth 1 https://github.com/ggerganov/llama.cpp {LLAMACPP_DIR}",
            cwd=LOCAL_MODELS_DIR
        )
        # Install conversion script requirements
        req_file = LLAMACPP_DIR / "requirements.txt"
        if req_file.exists():
            run(f"{sys.executable} -m pip install -r {req_file}", check=False)
        print(f"  ✅ llama.cpp cloned to: {LLAMACPP_DIR}")
    else:
        print(f"  ✅ llama.cpp already present at: {LLAMACPP_DIR}")


def step3_convert_to_gguf():
    """Convert HuggingFace safetensors model to GGUF format."""
    print("\n[3/4] Converting HuggingFace model to GGUF (Q4_K_M)...")

    convert_script = LLAMACPP_DIR / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        # Older llama.cpp uses convert.py
        convert_script = LLAMACPP_DIR / "convert.py"
    if not convert_script.exists():
        print("  ❌ llama.cpp conversion script not found.")
        print("     Try: pip install llama-cpp-python and skip this step.")
        sys.exit(1)

    LOCAL_GGUF_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Step A: Convert to unquantized GGUF first
    unquantized_gguf = LOCAL_MODELS_DIR / "mistral-vidyabot-f16.gguf"
    run(
        f"{sys.executable} {convert_script} "
        f"{LOCAL_HF_MODEL_DIR} "
        f"--outfile {unquantized_gguf} "
        f"--outtype f16"
    )
    print(f"  ✅ Unquantized GGUF created: {unquantized_gguf}")

    # Step B: Quantize to Q4_K_M (4-bit, ~4GB, optimal for CPU inference)
    # Try llama-quantize binary if built, otherwise use Python-based quantization
    quantize_bin = LLAMACPP_DIR / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = LLAMACPP_DIR / "quantize"  # Older path

    if quantize_bin.exists():
        run(f"{quantize_bin} {unquantized_gguf} {LOCAL_GGUF_PATH} Q4_K_M")
        # Clean up unquantized file
        unquantized_gguf.unlink(missing_ok=True)
        print(f"  ✅ Quantized to Q4_K_M: {LOCAL_GGUF_PATH}")
    else:
        # Skip quantization — use f16 directly (larger but works)
        print("  ⚠️  llama-quantize binary not found — using f16 GGUF (larger, ~13GB)")
        print("     To build quantize: cd backend/llm/models/llama.cpp && cmake -B build && cmake --build build -t llama-quantize")
        LOCAL_GGUF_PATH = unquantized_gguf
        print(f"  ✅ Using f16 GGUF: {LOCAL_GGUF_PATH}")

    return LOCAL_GGUF_PATH


def step4_create_ollama_model(gguf_path: Path):
    """Create the Ollama model from the GGUF file."""
    print("\n[4/4] Creating Ollama model 'mistral-vidyabot'...")

    modelfile_path = LOCAL_MODELS_DIR / "Modelfile"

    # Write the Modelfile pointing to our GGUF
    # Use absolute path for FROM directive
    abs_gguf = gguf_path.resolve()
    modelfile_content = f"""FROM {abs_gguf}

# VidyaBot fine-tuned model parameters
PARAMETER num_ctx 2048
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1

# System prompt baked into the model
SYSTEM "You are VidyaBot, an expert AI tutor for Indian school students studying NCERT curriculum. You give clear, concise, and accurate answers in 2-4 sentences. Always use correct scientific or mathematical terminology as found in NCERT textbooks."
"""
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    print(f"  ✅ Modelfile written: {modelfile_path}")

    # Create the model in Ollama
    result = run(
        f"ollama create mistral-vidyabot -f {modelfile_path}",
        check=False
    )
    if result.returncode == 0:
        print("  ✅ Ollama model 'mistral-vidyabot' created!")
        print("\n  Test it:")
        print('  ollama run mistral-vidyabot "What is photosynthesis?"')
    else:
        print("  ⚠️  Ollama create failed — make sure 'ollama serve' is running")
        print(f"     Manual command: ollama create mistral-vidyabot -f {modelfile_path}")


def main():
    print("=" * 60)
    print("  VidyaBot GGUF Conversion Pipeline")
    print("  Modal → HuggingFace → GGUF → Ollama")
    print("=" * 60)

    # Check if model already downloaded locally
    if LOCAL_HF_MODEL_DIR.exists() and any(LOCAL_HF_MODEL_DIR.iterdir()):
        print(f"\n  ✅ Model already downloaded at: {LOCAL_HF_MODEL_DIR}")
        skip = input("  Skip download step? [Y/n]: ").strip().lower()
        if skip != "n":
            print("  Skipping download...")
            step2_get_llamacpp()
            gguf_path = step3_convert_to_gguf()
            step4_create_ollama_model(gguf_path)
            return

    step1_download_from_modal()
    step2_get_llamacpp()
    gguf_path = step3_convert_to_gguf()
    step4_create_ollama_model(gguf_path)

    print("\n" + "=" * 60)
    print("  ✅ ALL STEPS COMPLETE")
    print()
    print("  Your fine-tuned model is ready:")
    print(f"  GGUF: {gguf_path}")
    print(f"  Ollama: mistral-vidyabot")
    print()
    print("  Update your .env file:")
    print("  OLLAMA_MODEL=mistral-vidyabot")
    print()
    print("  Or test directly:")
    print('  python -c "')
    print("  from backend.llm.ollama_client import OllamaClient")
    print("  c = OllamaClient(model='mistral-vidyabot')")
    print("  r = c.ask('You are a tutor.', 'What is photosynthesis?', 150)")
    print("  print(r.answer)")
    print('  "')
    print("=" * 60)


if __name__ == "__main__":
    main()
