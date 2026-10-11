"""Create a transparent row-level audit of the retired V2 development challenge."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "training_data" / "chat_intents_challenge_test.jsonl"
OUTPUT = ROOT / "docs" / "CHAT_CHALLENGE_AUDIT_V3.md"

FILLERS = {
    "شو بتنصح؟": "AMBIGUOUS",
    "بدي أعرف قبل القرار.": "UNNATURAL_SYNTHETIC",
    "هل بتقدر توضح؟": "CONTEXT_DEPENDENT",
    "هذا استفساري الوحيد.": "UNNATURAL_SYNTHETIC",
    "يعني كيف؟": "AMBIGUOUS",
    "بكلمات بسيطة.": "UNNATURAL_SYNTHETIC",
    "بدون ما أعمل طلب الآن.": "UNNATURAL_SYNTHETIC",
    "وأنا بانتظار الرد.": "UNNATURAL_SYNTHETIC",
    "إذا كانت الخدمة متاحة.": "UNNATURAL_SYNTHETIC",
    "للتخطيط للمشوار.": "UNNATURAL_SYNTHETIC",
}


def classify(row: dict) -> tuple[str, str]:
    text, intent = row["text"], row["intent"]
    if intent in {"confirmation", "cancellation"}:
        return "CONTEXT_DEPENDENT", "Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label."
    for filler, status in FILLERS.items():
        if filler in text:
            if filler == "بدون ما أعمل طلب الآن." and intent == "book_trip":
                return "CONTRADICTORY", "The suffix explicitly denies creating a request while the target label requests reservation."
            return status, f"Injected suffix ‘{filler}’ is not required by the target intent and changes or obscures the natural user meaning."
    return "VALID", "The text has a plausible standalone meaning for its assigned intent without an injected conflicting suffix."


def build() -> Path:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = {}
    lines = ["# V2 development challenge audit for V3", "", "## Decision", "", "This 150-row set is retained as a **development diagnostic only**. It must not be relabelled silently, trained on, used for V3 hyperparameter selection, or presented as the final unbiased benchmark. The row-level audit below records why.", "", "Status meanings: `VALID` = plausible standalone label; `AMBIGUOUS` = more than one plausible intent; `CONTRADICTORY` = target conflicts with text; `CONTEXT_DEPENDENT` = server conversation state is required; `UNNATURAL_SYNTHETIC` = generated filler makes the sentence implausible or distorts intent.", "", "| # | Intent | Status | Text | Reason |", "|---:|---|---|---|---|"]
    for number, row in enumerate(rows, 1):
        status, reason = classify(row); counts[status] = counts.get(status, 0) + 1
        text = row["text"].replace("|", "\\|")
        lines.append(f"| {number} | `{row['intent']}` | **{status}** | {text} | {reason} |")
    lines[4:4] = ["", "## Summary", "", *[f"- {name}: {count}" for name, count in sorted(counts.items())], ""]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(build())
