# app.py — Main entry point for VidyaBot Gradio Edition (Cross-platform local and HF Space)
import sys
import warnings
import subprocess
import time
import os

# Enforce UTF-8 encoding on standard streams to prevent Windows console encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Suppress Gradio's warning about Blocks parameters theme/css moving to launch()
warnings.filterwarnings("ignore", category=UserWarning, module="gradio")

print("🚀 VidyaBot Launch Sequence")
print("=" * 50)

# Start Ollama daemon on Linux (e.g. Hugging Face Spaces)
if sys.platform != "win32":
    print("📦 Starting Ollama daemon...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        
        # Pull base model in the background as fallback
        print("📥 Ensuring mistral:latest is available...")
        subprocess.Popen(
            ["ollama", "pull", "mistral:latest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"⚠️ Could not start Ollama: {e}")
else:
    print("💻 Windows environment detected. Assumes local Ollama is running.")

print("=" * 50)
print("🎯 Launching VidyaBot Gradio UI...")
print("=" * 50)

import gradio as gr
from backend.main import app as fastapi_app
from gradio_app import create_demo

demo = create_demo()
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
