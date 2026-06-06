# app.py — Main entry point for VidyaBot Gradio Edition
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
from backend.main import app as fastapi_app
from gradio_app import create_demo

demo = create_demo()
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)
