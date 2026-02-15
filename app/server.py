"""
Scan Auto-Crop — FastAPI Backend
Serves the crop engine as a REST API + static frontend files.
"""

import os
import uuid
import shutil
import base64
import io
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import cv2
import numpy as np
from PIL import Image

from core.cropper import crop_image, process_single_image

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Scan Auto-Crop", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temp storage for uploads and processed files
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "scan_autocrop_uploads")
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "scan_autocrop_output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _make_thumbnail(img_path, max_size=300):
    """Create a base64-encoded JPEG thumbnail."""
    img = Image.open(img_path)
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/status")
def health_check():
    return {"status": "ok", "engine": "5-tier-fallback"}


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """
    Upload image files. Returns a session ID and file list with thumbnails.
    """
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    uploaded = []

    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in valid_exts:
            continue

        file_path = os.path.join(session_dir, f.filename)
        with open(file_path, "wb") as out:
            content = await f.read()
            out.write(content)

        thumb = _make_thumbnail(file_path)
        img = Image.open(file_path)
        w, h = img.size

        uploaded.append({
            "filename": f.filename,
            "width": w,
            "height": h,
            "size_kb": round(len(content) / 1024, 1),
            "thumbnail": thumb,
        })

    return {
        "session_id": session_id,
        "count": len(uploaded),
        "files": uploaded,
    }


@app.post("/api/crop")
async def crop_files(session_id: str = Form(...)):
    """
    Crop all uploaded images in a session.
    Returns results with thumbnails of cropped images.
    """
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.exists(session_dir):
        raise HTTPException(status_code=404, detail="Session not found")

    output_dir = os.path.join(OUTPUT_DIR, session_id)
    os.makedirs(output_dir, exist_ok=True)

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    files = [f for f in os.listdir(session_dir)
             if os.path.splitext(f)[1].lower() in valid_exts]
    files.sort()

    results = []
    stats = {}

    for filename in files:
        input_path = os.path.join(session_dir, filename)
        output_path = os.path.join(output_dir, filename)

        result = process_single_image(input_path, output_path)

        # Generate thumbnail of cropped result
        thumb = _make_thumbnail(output_path)
        result["cropped_thumbnail"] = thumb

        # Original thumbnail
        result["original_thumbnail"] = _make_thumbnail(input_path)

        results.append(result)
        s = result["strategy"]
        stats[s] = stats.get(s, 0) + 1

    total = len(results)
    cropped_count = sum(1 for r in results
                        if r["strategy"] not in ("original", "no_crop_needed", "error_fallback"))

    return {
        "session_id": session_id,
        "total": total,
        "cropped": cropped_count,
        "unchanged": total - cropped_count,
        "success_rate": round(cropped_count / total * 100, 1) if total > 0 else 0,
        "stats": stats,
        "results": results,
    }


@app.get("/api/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """Download a single cropped image."""
    file_path = os.path.join(OUTPUT_DIR, session_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="image/jpeg", filename=filename)


@app.post("/api/crop-folder")
async def crop_folder(folder_path: str = Form(...)):
    """
    Crop all images in a local folder path.
    Saves output to '{folder} - Cropped/' next to originals.
    """
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder_path}")

    output_folder = folder_path.rstrip("/\\") + " - Cropped"
    os.makedirs(output_folder, exist_ok=True)

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    files = [f for f in os.listdir(folder_path)
             if os.path.splitext(f)[1].lower() in valid_exts]
    files.sort()

    results = []
    stats = {}

    for filename in files:
        input_path = os.path.join(folder_path, filename)
        output_path = os.path.join(output_folder, filename)

        result = process_single_image(input_path, output_path)
        results.append(result)
        s = result["strategy"]
        stats[s] = stats.get(s, 0) + 1

    total = len(results)
    cropped_count = sum(1 for r in results
                        if r["strategy"] not in ("original", "no_crop_needed", "error_fallback"))

    return {
        "total": total,
        "cropped": cropped_count,
        "output_folder": output_folder,
        "success_rate": round(cropped_count / total * 100, 1) if total > 0 else 0,
        "stats": stats,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Serve Frontend
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
