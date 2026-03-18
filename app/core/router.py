"""
Crop Router — Three-tier routing for crop decisions.

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
# Route + Validate
# ---------------------------------------------------------------------------
def route_crop(original_img, cropped_img, strategy, confidence, validation, progress_callback=None):
    """
    Route a crop result through the three-tier system.

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
    if cropped_img is None:
        # No crop proposed by CV. But the image might still have a border
        # that the CV engine couldn't detect. Ask the LLM if enabled.
        no_crop_result = {
            "cropped_img": None,
            "strategy": strategy,
            "confidence": confidence,
            "validation": validation,
            "tier": 0,
            "tier_label": "no_crop",
            "llm_result": None,
        }

        # Only ask LLM if CV explicitly said "no crop needed" (not a rejection)
        if strategy in ("no_crop_needed", "original"):
            cfg = _load_config()
            llm_cfg = cfg.get("llm", {})

            if llm_cfg.get("enabled", True):
                from core.llm_validator import validate_with_llm, is_available

                if is_available():
                    model = llm_cfg.get("model", "qwen3.5:2b")
                    timeout = llm_cfg.get("timeout_seconds", 15)

                    if progress_callback:
                        progress_callback("llm", f"Analyzing with LLM ({model}, takes ~30s)...")
                    logger.info(f"No-crop check: asking LLM if border exists")
                    llm_result = validate_with_llm(
                        original_img, model=model, timeout=timeout
                    )
                    no_crop_result["llm_result"] = llm_result

                    if llm_result["verdict"] == "SAFE":
                        # LLM sees a border that CV missed -- flag for user
                        no_crop_result["strategy"] = "llm_border_detected"
                        no_crop_result["tier"] = 2
                        no_crop_result["tier_label"] = "llm_border_detected"
                        logger.info(
                            f"LLM detected border CV missed: {llm_result['reason']}"
                        )
                    else:
                        # LLM agrees no border -- genuinely no crop needed
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

    elif tier == 2:
        # Medium confidence — ask LLM
        cfg = _load_config()
        llm_cfg = cfg.get("llm", {})

        if not llm_cfg.get("enabled", True):
            # LLM disabled — fall back to auto-approve
            result["tier_label"] = "llm_disabled"
            logger.info(f"Tier 2: LLM disabled, auto-approving (confidence={confidence})")
            return result

        from core.llm_validator import validate_with_llm, is_available

        if not is_available():
            # Ollama not running — use fallback
            fallback = llm_cfg.get("fallback_on_error", "SKIP")
            result["llm_result"] = {
                "verdict": fallback,
                "confidence": "LOW",
                "reason": "Ollama not available",
                "time_ms": 0,
            }
            if fallback == "SKIP":
                result["cropped_img"] = None
                result["strategy"] = "llm_unavailable"
                result["tier_label"] = "llm_unavailable"
            logger.info(f"Tier 2: Ollama unavailable, fallback={fallback}")
            return result

        # Call LLM
        model = llm_cfg.get("model", "qwen3.5:2b")
        timeout = llm_cfg.get("timeout_seconds", 15)

        if progress_callback:
            progress_callback("llm", f"Validating crop with LLM ({model}, takes ~30s)...")
        logger.info(f"Tier 2: Calling LLM (confidence={confidence}, model={model})")
        llm_result = validate_with_llm(
            original_img, model=model, timeout=timeout
        )
        result["llm_result"] = llm_result

        if llm_result["verdict"] == "SAFE":
            result["tier_label"] = "llm_approved"
            logger.info(f"Tier 2: LLM approved ({llm_result['reason']})")
        elif llm_result["verdict"] == "RISKY":
            # LLM says risky — reject the crop, keep original
            result["cropped_img"] = None
            result["strategy"] = "llm_rejected"
            result["tier_label"] = "llm_rejected"
            logger.info(f"Tier 2: LLM rejected ({llm_result['reason']})")
        else:
            # SKIP or unparseable — use fallback
            fallback = llm_cfg.get("fallback_on_error", "SKIP")
            if fallback == "SKIP":
                result["cropped_img"] = None
                result["strategy"] = "llm_skip"
                result["tier_label"] = "llm_skip"
            logger.info(f"Tier 2: LLM returned SKIP, fallback={fallback}")

        return result

    else:
        # Tier 3: Low confidence — flag for review, keep original
        result["cropped_img"] = None
        result["strategy"] = "flagged_review"
        result["tier_label"] = "flagged_review"
        logger.info(f"Tier 3: Flagged for review (confidence={confidence})")
        return result
