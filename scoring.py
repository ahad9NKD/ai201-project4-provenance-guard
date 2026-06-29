from __future__ import annotations

from dataclasses import dataclass

from signal_one import SignalResult


@dataclass
class CombinedResult:
    attribution: str
    confidence: float
    combined_score: float
    label: str
    label_category: str

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution": self.attribution,
            "confidence": round(self.confidence, 4),
            "combined_score": round(self.combined_score, 4),
            "label": self.label,
            "label_category": self.label_category,
        }


HIGH_AI_LABEL = "This text is likely AI-generated. We are fairly confident because multiple signals point in the same direction."
HIGH_HUMAN_LABEL = "This text is likely human-written. We are fairly confident because multiple signals point in the same direction."
UNCERTAIN_LABEL = "We cannot confidently tell whether this text was written by a human or AI. The signals are mixed or weak."


def combine_signals(signal_one: SignalResult, signal_two: SignalResult) -> CombinedResult:
    groq_score = float(signal_one.score)
    stylometric_score = float(signal_two.score)
    base = 0.6 * groq_score + 0.4 * stylometric_score
    disagreement = abs(groq_score - stylometric_score)
    calibrated = 0.5 + (base - 0.5) * (1 - 0.5 * disagreement)
    confidence = max(0.0, min(1.0, calibrated))

    if confidence >= 0.75:
        attribution = "likely_ai"
        label = HIGH_AI_LABEL
        category = "high_confidence_ai"
    elif confidence <= 0.25:
        attribution = "likely_human"
        label = HIGH_HUMAN_LABEL
        category = "high_confidence_human"
    else:
        attribution = "uncertain"
        label = UNCERTAIN_LABEL
        category = "uncertain"

    return CombinedResult(
        attribution=attribution,
        confidence=confidence,
        combined_score=base,
        label=label,
        label_category=category,
    )

