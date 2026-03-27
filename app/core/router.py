"""
Crop Router — Three-tier routing for crop decisions.

Supports two modes (configurable in config.yaml):
  post_cv: CV crops first, LLM validates ambiguous crops (default)
  pre_cv:  LLM screens image first, CV only runs if LLM says border exists
  off:     No LLM, pure CV

Tier 1 (High confidence, >threshold): Auto-crop, skip LLM
Tier 2 (Medium confidence): Validate with LLM
Tier 3 (Low confidence, <threshold): Flag for review, keep original

Loads thresholds from config.yaml.
"""

import logging
import os

import yaml

logger = logging.getLogger("crop_router")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
_config = None


def _load_config():
    """Load config.yaml from the app directory."""
    global _config
    if _config is not None:
        return _config

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(config_path, "r") as f:
            _config = yaml.safe_load(f)
        logger.info(f"Config loaded from {config_path}")
    except Exception as e:
        logger.warning(f"Failed to load config: {e}. Using defaults.")
        _config = {}

    return _config


def get_config():
    """Public access to the loaded config."""
    return _load_config()


def reload_config(new_cfg=None):
    """
    Hot-reload config at runtime (used by /api/llm-toggle).
    If new_cfg is provided, use it directly. Otherwise re-read from disk.
    """
    global _config
    if new_cfg is not None:
        _config = new_cfg
    else:
        _config = None  # Force re-read from disk
        _load_config()


def _get_llm_mode():
    """Get the current LLM mode: 'off', 'post_cv', 'pre_cv'."""
    cfg = _load_config()
    llm_cfg = cfg.get("llm", {})
    if not llm_cfg.get("enabled", True):
        return "off"
    return llm_cfg.get("mode", "post_cv")


# ---------------------------------------------------------------------------
# Tier Classification
# ---------------------------------------------------------------------------
def classify_tier(confidence):
    """
    Classify a confidence score into a processing tier.

    Returns:
        int: 1, 2, or 3
        str: tier label
    """
    cfg = _load_config()
    t1 = cfg.get("confidence", {}).get("tier1_threshold", 90)
    t2 = cfg.get("confidence", {}).get("tier2_threshold", 40)

    if confidence >= t1:
        return 1, "auto_approved"
    elif confidence >= t2:
        return 2, "needs_llm"
    else:
        return 3, "flagged_review"


# ---------------------------------------------------------------------------
# LLM Helper (shared by both modes)
# ---------------------------------------------------------------------------
def _call_llm(original_img, progress_callback=None, purpose="Analyzing"):
    """
    Call the LLM. Returns (llm_result_dict, available: bool).
    Returns (None, False) if LLM is off/unavailable.
    """
    cfg = _load_config()
    llm_cfg = cfg.get("llm", {})

    from core.llm_validator import validate_with_llm, is_available

    if not is_available():
        return None, False

    model = llm_cfg.get("model", "qwen3.5:2b")
    timeout = llm_cfg.get("timeout_seconds", 60)

    if progress_callback:
        progress_callback("llm", f"{purpose} with LLM ({model})...")
    logger.info(f"Calling LLM ({purpose}, model={model})")

    llm_result = validate_with_llm(original_img, model=model, timeout=timeout)
    return llm_result, True


# ---------------------------------------------------------------------------
# MODE: pre_cv — LLM screens first, then CV crops
# ---------------------------------------------------------------------------
def route_pre_cv(original_img, progress_callback=None):
    """
    LLM-first mode. Ask LLM: 'does this image have a scanner border?'
    If YES (SAFE) -> tell CV to crop it.
    If NO (RISKY) -> skip CV entirely, keep original.

    Returns:
        dict with keys: should_crop (bool), llm_result, tier_label
    """
    llm_result, available = _call_llm(
        original_img, progress_callback, purpose="Pre-screening"
    )

    if not available or llm_result is None:
        # LLM unavailable -- fall through to CV as normal
        return {
            "should_crop": True,   # Let CV try anyway
            "llm_result": {"verdict": "SKIP", "confidence": "LOW",
                           "reason": "Ollama not available", "time_ms": 0},
            "tier_label": "llm_unavailable",
        }

    if llm_result["verdict"] == "SAFE":
        # LLM says border exists -> let CV crop
        logger.info(f"Pre-CV: LLM says border exists, proceeding to CV")
        return {
            "should_crop": True,
            "llm_result": llm_result,
            "tier_label": "llm_prescreened",
        }
    elif llm_result["verdict"] == "RISKY":
        # LLM says no border -> skip CV entirely
        logger.info(f"Pre-CV: LLM says no border, skipping CV")
        return {
            "should_crop": False,
            "llm_result": llm_result,
            "tier_label": "llm_no_border",
        }
    else:
        # SKIP/unparseable -> let CV try
        logger.info(f"Pre-CV: LLM unclear, letting CV decide")
        return {
            "should_crop": True,
            "llm_result": llm_result,
            "tier_label": "llm_skip",
        }


# ---------------------------------------------------------------------------
# MODE: post_cv — Current behavior (CV first, LLM validates)
# ---------------------------------------------------------------------------
def route_crop(original_img, cropped_img, strategy, confidence, validation,
               progress_callback=None):
    """
    Route a crop result through the three-tier system (post_cv mode).

    Args:
        original_img: Original BGR image
        cropped_img: Proposed crop (or None)
        strategy: CV strategy name
        confidence: int 0-100
        validation: dict from validators
        progress_callback: Optional callable(step: str, detail: str)

    Returns:
        dict: Complete routing result with keys:
            cropped_img, strategy, confidence, validation,
            tier, tier_label, llm_result (if applicable)
    """
    mode = _get_llm_mode()

    if cropped_img is None:
        # No crop proposed by CV. Ask LLM if border exists (post_cv only).
        no_crop_result = {
            "cropped_img": None,
            "strategy": strategy,
            "confidence": confidence,
            "validation": validation,
            "tier": 0,
            "tier_label": "no_crop",
            "llm_result": None,
        }

        # Only ask LLM if CV explicitly said "no crop needed" and mode is post_cv
        if strategy in ("no_crop_needed", "original") and mode == "post_cv":
            llm_result, available = _call_llm(
                original_img, progress_callback, purpose="Checking for missed border"
            )
            if llm_result:
                no_crop_result["llm_result"] = llm_result
                if llm_result["verdict"] == "SAFE":
                    no_crop_result["strategy"] = "llm_border_detected"
                    no_crop_result["tier"] = 2
                    no_crop_result["tier_label"] = "llm_border_detected"
                    logger.info(
                        f"LLM detected border CV missed: {llm_result['reason']}"
                    )
                else:
                    no_crop_result["tier_label"] = "llm_confirmed_no_crop"
                    logger.info(
                        f"LLM confirms no border: {llm_result['reason']}"
                    )

        return no_crop_result

    tier, tier_label = classify_tier(confidence)

    result = {
        "cropped_img": cropped_img,
        "strategy": strategy,
        "confidence": confidence,
        "validation": validation,
        "tier": tier,
        "tier_label": tier_label,
        "llm_result": None,
    }

    if tier == 1:
        # High confidence — auto-approve
        logger.info(f"Tier 1: Auto-approved (confidence={confidence})")
        return result

    elif tier == 2 and mode == "post_cv":
        # Medium confidence — ask LLM to validate
        llm_result, available = _call_llm(
            original_img, progress_callback, purpose="Validating crop"
        )

        if not available:
            cfg = _load_config()
            fallback = cfg.get("llm", {}).get("fallback_on_error", "SKIP")
            result["llm_result"] = {
                "verdict": fallback, "confidence": "LOW",
                "reason": "Ollama not available", "time_ms": 0,
            }
            if fallback == "SKIP":
                result["cropped_img"] = None
                result["strategy"] = "llm_unavailable"
                result["tier_label"] = "llm_unavailable"
            return result

        result["llm_result"] = llm_result

        if llm_result["verdict"] == "SAFE":
            result["tier_label"] = "llm_approved"
            logger.info(f"Tier 2: LLM approved ({llm_result['reason']})")
        elif llm_result["verdict"] == "RISKY":
            result["cropped_img"] = None
            result["strategy"] = "llm_rejected"
            result["tier_label"] = "llm_rejected"
            logger.info(f"Tier 2: LLM rejected ({llm_result['reason']})")
        else:
            cfg = _load_config()
            fallback = cfg.get("llm", {}).get("fallback_on_error", "SKIP")
            if fallback == "SKIP":
                result["cropped_img"] = None
                result["strategy"] = "llm_skip"
                result["tier_label"] = "llm_skip"
            logger.info(f"Tier 2: LLM returned SKIP, fallback={fallback}")

        return result

    elif tier == 2 and mode != "post_cv":
        # LLM is off or pre_cv already ran — auto-approve Tier 2
        result["tier_label"] = "llm_disabled"
        logger.info(f"Tier 2: LLM mode={mode}, auto-approving")
        return result

    else:
        # Tier 3: Low confidence — flag for review, keep original
        result["cropped_img"] = None
        result["strategy"] = "flagged_review"
        result["tier_label"] = "flagged_review"
        logger.info(f"Tier 3: Flagged for review (confidence={confidence})")
        return result
