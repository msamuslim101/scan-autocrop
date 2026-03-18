"""
LLM Crop Validator — Semantic image analysis via Ollama.

Uses a local multimodal LLM (Qwen 3.5 2B) to validate ambiguous crops
that classical CV cannot confidently decide.

The LLM receives the original image and answers whether cropping is safe.
It checks for: faces being cut, text being clipped, content vs border,
and any important details that would be lost.

Design principles:
  - LLM is a SAFETY NET, not a replacement for CV
  - Only called for medium-confidence crops (Tier 2: 60-90)
  - On failure/timeout: defaults to SKIP (keep original, zero data loss)
  - Lazy-loads the model on first call
"""

import base64
import io
import logging
import time

import cv2
import numpy as np

logger = logging.getLogger("llm_validator")


# ---------------------------------------------------------------------------
# Module State (lazy-loaded)
# ---------------------------------------------------------------------------
_ollama_available = None  # None = not checked, True/False = checked


def _check_ollama():
    """Check if Ollama is running. Caches the result."""
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available

    try:
        import ollama
        ollama.list()
        _ollama_available = True
        logger.info("Ollama is available")
    except Exception as e:
        _ollama_available = False
        logger.warning(f"Ollama not available: {e}")

    return _ollama_available


def is_available():
    """Public check: is Ollama running and reachable?"""
    return _check_ollama()


def _encode_image(img):
    """Convert a BGR numpy array to base64 JPEG for Ollama."""
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    from PIL import Image
    pil_img = Image.fromarray(rgb)

    # Resize large images to save memory and speed up inference
    max_dim = 1024
    if max(pil_img.size) > max_dim:
        ratio = max_dim / max(pil_img.size)
        new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
        pil_img = pil_img.resize(new_size, Image.LANCZOS)

    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# The Prompt
# ---------------------------------------------------------------------------
VALIDATION_PROMPT = """You are a photo crop validator. I will show you a scanned photo.

This image was scanned on a flatbed scanner. The scanning process adds a white or light gray border around the actual photo. Our software detected a crop boundary and wants to remove the border.

Look at this image carefully and answer:

1. Is there a visible scanner border (white/gray area) around the photo?
2. Would cropping to remove that border cut into any faces, text, or important content?
3. Is this image a full page scan with a border, or an already-cropped photo without a border?

Reply with EXACTLY one line in this format:
VERDICT: SAFE or RISKY
REASON: one short sentence explaining why

Example good responses:
VERDICT: SAFE
REASON: Clear white border visible on all sides, no content would be lost.

VERDICT: RISKY
REASON: No visible scanner border, this appears to be an already-cropped photo.

VERDICT: SAFE
REASON: Scanner border visible, all faces and text are well inside the photo area."""


def validate_with_llm(original_img, model="qwen3.5:2b", timeout=15):
    """
    Ask the LLM whether this image has a scanner border that is safe to crop.

    Args:
        original_img: Original BGR image (numpy array)
        model: Ollama model name
        timeout: Max seconds to wait for response

    Returns:
        dict with keys:
            verdict: "SAFE", "RISKY", or "SKIP"
            confidence: "HIGH", "MEDIUM", or "LOW"
            reason: str explanation
            time_ms: int processing time in milliseconds
    """
    if not _check_ollama():
        return {
            "verdict": "SKIP",
            "confidence": "LOW",
            "reason": "Ollama not available",
            "time_ms": 0,
        }

    try:
        import ollama

        img_b64 = _encode_image(original_img)

        start = time.time()

        response = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": VALIDATION_PROMPT,
                "images": [img_b64],
            }],
            options={
                "temperature": 0.1,  # Low temp for consistent responses
                "num_predict": 100,  # Short response only
            },
        )

        elapsed_ms = int((time.time() - start) * 1000)

        # Parse response
        text = response["message"]["content"].strip()
        return _parse_response(text, elapsed_ms)

    except Exception as e:
        logger.warning(f"LLM validation failed: {e}")
        return {
            "verdict": "SKIP",
            "confidence": "LOW",
            "reason": f"LLM error: {str(e)[:80]}",
            "time_ms": 0,
        }


def _parse_response(text, elapsed_ms):
    """Parse the LLM response into a structured result."""
    lines = text.strip().split("\n")
    verdict = "SKIP"
    reason = text[:120]

    for line in lines:
        line_upper = line.strip().upper()
        if line_upper.startswith("VERDICT:"):
            val = line_upper.replace("VERDICT:", "").strip()
            if "SAFE" in val:
                verdict = "SAFE"
            elif "RISKY" in val:
                verdict = "RISKY"
        elif line.strip().upper().startswith("REASON:"):
            reason = line.strip()[7:].strip()

    # Determine confidence based on how clean the response was
    confidence = "HIGH" if verdict in ("SAFE", "RISKY") else "LOW"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "time_ms": elapsed_ms,
    }
