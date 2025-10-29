# app.py
"""
Standalone launcher for the Gradio UI (no FastAPI mount).
Run with: uv run app.py
"""

import os
from ui.gradio_ui import build_ui

# Optional environment variables to customize host/port
UI_HOST = os.getenv("UI_HOST", "127.0.0.1")   # or "0.0.0.0" for LAN access
UI_PORT = int(os.getenv("UI_PORT", "7860"))   # default Gradio port

def main():
    demo = build_ui()          # returns a gr.Blocks app
    # Enable queue for smooth UX (streaming-ready), open browser once
    demo.queue().launch(
        server_name=UI_HOST,
        server_port=UI_PORT,
        share=False,            # set True if you need a public Gradio link
        inbrowser=True          # auto-open the browser tab
    )

if __name__ == "__main__":
    main()