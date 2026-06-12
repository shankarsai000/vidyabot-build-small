"""
modal_convert_gguf.py — Download GGUF from Modal Volume & Register with Ollama

Run this AFTER modal_finetune.py completes.

Steps:
1. Download the quantized GGUF model directly from Modal Volume to local disk
2. Create/update the Ollama model pointing to the downloaded GGUF file

Usage (from project root):
    python modal_convert_gguf.py
"""

import subprocess
import sys
from pathlib import Path

# Enforce UTF-8 encoding on standard streams to prevent Windows console encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
VOLUME_NAME = "vidyabot-model-output"
REMOTE_GGUF_FILENAME = "mistral-vidyabot.Q4_K_M.gguf"
LOCAL_MODELS_DIR = Path("backend/llm/models")
LOCAL_GGUF_PATH = LOCAL_MODELS_DIR / REMOTE_GGUF_FILENAME


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
    """Download the GGUF model file from Modal Volume to local disk."""
    print(f"\n[1/2] Downloading GGUF model '{REMOTE_GGUF_FILENAME}' from Modal Volume '{VOLUME_NAME}'...")
    LOCAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Use the Modal CLI in the virtual environment if available
    python_dir = Path(sys.executable).parent
    modal_bin = python_dir / "modal.exe" if (python_dir / "modal.exe").exists() else (python_dir / "modal" if (python_dir / "modal").exists() else "modal")

    cmd = (
        f'"{modal_bin}" volume get {VOLUME_NAME} '
        f"{REMOTE_GGUF_FILENAME} {LOCAL_MODELS_DIR}"
    )
    run(cmd)
    
    # Check if download succeeded
    if LOCAL_GGUF_PATH.exists():
        print(f"  ✅ Model downloaded successfully to: {LOCAL_GGUF_PATH}")
    else:
        print(f"  ❌ GGUF file not found at {LOCAL_GGUF_PATH} after download.")
        sys.exit(1)


def step2_create_ollama_model():
    """Create the Ollama model from the downloaded GGUF file."""
    print("\n[2/2] Creating Ollama model 'mistral-vidyabot'...")

    modelfile_path = LOCAL_MODELS_DIR / "Modelfile"

    # Write the Modelfile pointing to our GGUF
    abs_gguf = LOCAL_GGUF_PATH.resolve()
    
    # Check if Modelfile exists and update it
    modelfile_content = f"""FROM {abs_gguf}

# VidyaBot fine-tuned model parameters
PARAMETER num_ctx 2048
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER stop "<s>"
PARAMETER stop "</s>"
PARAMETER stop "[INST]"
PARAMETER stop "[/INST]"

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
    print("  VidyaBot GGUF Download & Registration Pipeline")
    print("  Modal Volume -> Local GGUF -> Ollama")
    print("=" * 60)

    # Check if model already downloaded locally
    if LOCAL_GGUF_PATH.exists():
        print(f"\n  ✅ GGUF Model already exists at: {LOCAL_GGUF_PATH}")
        if not sys.stdin.isatty():
            print("  Non-interactive mode detected. Skipping download step...")
            skip = "y"
        else:
            skip = input("  Skip download step? [Y/n]: ").strip().lower()
        if skip != "n":
            print("  Skipping download...")
            step2_create_ollama_model()
            return

    step1_download_from_modal()
    step2_create_ollama_model()

    print("\n" + "=" * 60)
    print("  ✅ ALL STEPS COMPLETE")
    print()
    print("  Your fine-tuned model is ready:")
    print(f"  GGUF: {LOCAL_GGUF_PATH}")
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
