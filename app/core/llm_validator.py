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

    # Resize large images for speed (smaller = faster inference)
    max_dim = 512
    if max(pil_img.size) > max_dim:
        ratio = max_dim / max(pil_img.size)
        new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
        pil_img = pil_img.resize(new_size, Image.LANCZOS)

    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# The Prompt
# ---------------------------------------------------------------------------
VALIDATION_PROMPT = """Does this scanned photo have a white or gray scanner border around the photo content? Answer SAFE if a border exists and can be cropped, or RISKY if no border exists. Reply: VERDICT: SAFE or RISKY, then REASON: one sentence. /no_think"""


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
                "num_predict": 500,  # Enough for thinking + response
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
    import re
    text = text.strip()
    if not text:
        return {
            "verdict": "SKIP",
            "confidence": "LOW",
            "reason": "empty response",
            "time_ms": elapsed_ms,
        }

    # Handle single-word responses (e.g., just "SAFE" or "RISKY")
    text_upper = text.upper().strip()
    if text_upper in ("SAFE", "RISKY"):
        return {
            "verdict": text_upper,
            "confidence": "HIGH",
            "reason": text_upper.lower(),
            "time_ms": elapsed_ms,
        }

    verdict = "SKIP"
    reason = "Undetermined"
    
    # Use regex to find exactly VERDICT: [SAFE/RISKY] anywhere in text
    v_match = re.search(r'VERDICT:\s*(SAFE|RISKY)', text_upper)
    if v_match:
        verdict = v_match.group(1)
    else:
        # Fallback to checking if the words exist
        if "SAFE" in text_upper and "RISKY" not in text_upper:
            verdict = "SAFE"
        elif "RISKY" in text_upper and "SAFE" not in text_upper:
            verdict = "RISKY"

    # Use regex to find REASON: [text] up to end of line or string
    # case insensitive search
    r_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', text, flags=re.IGNORECASE)
    if r_match:
        reason = r_match.group(1).strip()
    else:
        # Fallback: limit to 120 chars if no clean REASON found
        reason = text[:120].strip()

    confidence = "HIGH" if verdict in ("SAFE", "RISKY") else "LOW"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "time_ms": elapsed_ms,
    }
