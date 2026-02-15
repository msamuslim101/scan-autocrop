"""
Scan Auto-Crop — Entry Point
Starts the FastAPI server and opens the browser.
"""

import os
import sys
import webbrowser
import threading
import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def open_browser():
    """Open browser after a short delay to let the server start."""
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    # Change to app directory so imports work
    app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)
    sys.path.insert(0, app_dir)

    print(f"[Scan Auto-Crop] Starting server at http://{HOST}:{PORT}")
    print(f"[Scan Auto-Crop] Opening browser...")

    # Open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
