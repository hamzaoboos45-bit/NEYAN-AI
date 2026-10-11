"""Load NEYAN's fine-tuned AraBERT intent delta once per process.

Only the supervised delta is shipped; the public AraBERT base remains loaded
through the existing optional model-acquisition path.  Failures return no
prediction so the established semantic/rule fallback remains available.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import config

_lock = threading.Lock()
_cache: dict[str, dict] = {}

ARTIFACT_SPECS = {
    "v1": {"metadata_file": "chat_intent_metadata.json", "state_file": "arabert_intent_delta.pt", "format": "neyan-arabert-intent-head-v1"},
    "v2": {"metadata_file": "chat_intent_metadata_v2.json", "state_file": "arabert_intent_delta_v2.pt", "format": "neyan-arabert-intent-delta-v2"},
}


def model_directory() -> Path:
    return Path(getattr(config, "TRAINED_CHAT_MODEL_PATH", "") or Path(__file__).with_name("models"))


def selected_version(version: str | None = None) -> str | None:
    """Resolve an explicit artifact version without silently changing it."""
    value = str(version if version is not None else getattr(config, "TRAINED_CHAT_MODEL_VERSION", "v1")).strip().lower()
    return value if value in ARTIFACT_SPECS else None


def artifact_spec(version: str | None = None) -> dict | None:
    resolved = selected_version(version)
    return dict(ARTIFACT_SPECS[resolved]) if resolved else None


def _entry(version: str) -> dict:
    return _cache.setdefault(version, {"tokenizer": None, "model": None, "metadata": None, "error": None})


def validate_metadata(metadata: dict, version: str) -> None:
    spec = artifact_spec(version)
    if not spec or metadata.get("format") != spec["format"] or not isinstance(metadata.get("labels"), list) or not metadata["labels"]:
        raise ValueError("trained chat-model metadata is invalid")
    if metadata.get("state_file") != spec["state_file"]:
        raise ValueError("trained chat-model state file does not match selected version")
    if version == "v2" and metadata.get("dataset_version") != "v2":
        raise ValueError("V2 metadata must declare dataset_version v2")


def _load(version: str | None = None) -> bool:
    resolved = selected_version(version)
    if not config.ENABLE_AI_NLP:
        return False
    if not resolved:
        return False
    entry = _entry(resolved)
    if entry["model"] is not None:
        return True
    if entry["error"] is not None:
        return False
    with _lock:
        if entry["model"] is not None:
            return True
        if entry["error"] is not None:
            return False
        try:
            directory = model_directory()
            spec = ARTIFACT_SPECS[resolved]
            with (directory / spec["metadata_file"]).open(encoding="utf-8") as handle:
                metadata = json.load(handle)
            validate_metadata(metadata, resolved)
            state_path = directory / spec["state_file"]
            if not state_path.is_file():
                raise FileNotFoundError(f"selected {resolved} trained-model artifact is missing")
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            base_model = metadata.get("base_model") or config.ARABERT_MODEL_NAME
            tokenizer = AutoTokenizer.from_pretrained(base_model)
            model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=len(metadata["labels"]), ignore_mismatched_sizes=True)
            model.load_state_dict(torch.load(state_path, map_location="cpu", weights_only=True), strict=False)
            model.eval()
            entry.update(tokenizer=tokenizer, model=model, metadata=metadata)
            return True
        except Exception as exc:
            entry["error"] = str(exc)
            return False


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()


def is_available(version: str | None = None) -> bool:
    return _load(version)


def load_error(version: str | None = None) -> str | None:
    resolved = selected_version(version)
    if not resolved:
        return "TRAINED_CHAT_MODEL_VERSION must be v1 or v2"
    _load(resolved)
    return _entry(resolved)["error"]


def classify_for_version(text: str, version: str) -> tuple[str | None, float]:
    resolved = selected_version(version)
    if not text or not text.strip() or not resolved or not _load(resolved):
        return None, 0.0
    try:
        import torch
        entry = _entry(resolved)
        with torch.no_grad():
            tokens = entry["tokenizer"](text, return_tensors="pt", truncation=True, max_length=int(entry["metadata"].get("max_sequence_length", 64)), padding=True)
            probabilities = torch.softmax(entry["model"](**tokens).logits, dim=-1)[0]
            confidence, index = torch.max(probabilities, dim=0)
        return entry["metadata"]["labels"][int(index.item())], round(float(confidence.item()), 4)
    except Exception:
        return None, 0.0


def classify(text: str) -> tuple[str | None, float]:
    """Production path, controlled by TRAINED_CHAT_MODEL_VERSION (default V1)."""
    return classify_for_version(text, getattr(config, "TRAINED_CHAT_MODEL_VERSION", "v1"))


def classify_many_for_version(texts: list[str], version: str) -> list[tuple[str | None, float]]:
    """Batch helper for offline evaluation; runtime chat still uses classify."""
    resolved = selected_version(version)
    if not texts or not resolved or not _load(resolved):
        return [(None, 0.0) for _ in texts]
    try:
        import torch
        entry = _entry(resolved)
        with torch.no_grad():
            tokens = entry["tokenizer"](texts, return_tensors="pt", truncation=True, max_length=int(entry["metadata"].get("max_sequence_length", 64)), padding=True)
            probabilities = torch.softmax(entry["model"](**tokens).logits, dim=-1)
            values, indices = torch.max(probabilities, dim=-1)
        return [(entry["metadata"]["labels"][int(index)], round(float(value), 4)) for value, index in zip(values.tolist(), indices.tolist())]
    except Exception:
        return [(None, 0.0) for _ in texts]


def classify_many(texts: list[str]) -> list[tuple[str | None, float]]:
    return classify_many_for_version(texts, getattr(config, "TRAINED_CHAT_MODEL_VERSION", "v1"))
