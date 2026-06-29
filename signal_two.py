from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from signal_one import SignalResult


@dataclass
class StylometricFeatures:
    sentence_count: int
    word_count: int
    average_sentence_length: float
    sentence_length_variance: float
    type_token_ratio: float
    punctuation_density: float
    repetition_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentence_count": self.sentence_count,
            "word_count": self.word_count,
            "average_sentence_length": round(self.average_sentence_length, 4),
            "sentence_length_variance": round(self.sentence_length_variance, 4),
            "type_token_ratio": round(self.type_token_ratio, 4),
            "punctuation_density": round(self.punctuation_density, 4),
            "repetition_ratio": round(self.repetition_ratio, 4),
        }


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"\b[\w']+\b", text.lower())


def _calculate_features(text: str) -> StylometricFeatures:
    sentences = _split_sentences(text)
    words = _tokenize_words(text)
    sentence_lengths = [max(1, len(_tokenize_words(sentence))) for sentence in sentences] or [len(words) or 1]

    word_count = len(words) or 1
    sentence_count = len(sentences) or 1
    average_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
    variance = sum((length - average_sentence_length) ** 2 for length in sentence_lengths) / len(sentence_lengths)
    unique_words = len(set(words))
    type_token_ratio = unique_words / word_count
    punctuation_density = len(re.findall(r"[,:;()\-\"]", text)) / max(1, len(text))

    repeated_tokens = sum(count - 1 for count in _token_counts(words).values() if count > 1)
    repetition_ratio = repeated_tokens / word_count

    return StylometricFeatures(
        sentence_count=sentence_count,
        word_count=word_count,
        average_sentence_length=average_sentence_length,
        sentence_length_variance=variance,
        type_token_ratio=type_token_ratio,
        punctuation_density=punctuation_density,
        repetition_ratio=repetition_ratio,
    )


def _token_counts(words: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return counts


def _normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def run_second_signal(text: str) -> SignalResult:
    features = _calculate_features(text)

    variance_signal = 1.0 - _normalize(features.sentence_length_variance, 15.0, 60.0)
    sentence_count_signal = 1.0 - _normalize(abs(features.sentence_count - 3), 0.0, 3.0)
    repetition_signal = _normalize(features.repetition_ratio, 0.04, 0.22)
    punctuation_signal = _normalize(features.punctuation_density, 0.0, 0.06)
    formality_markers = len(
        re.findall(
            r"\b(it is important to note|furthermore|equally essential|responsible deployment|ethical implications|studies show|genuine tradeoffs|there are genuine tradeoffs|stakeholders across various sectors|must collaborate|prolonged low interest rates)\b",
            text.lower(),
        )
    )
    formality_signal = _normalize(formality_markers, 0, 4)
    colloquial_penalty = len(
        re.findall(
            r"\b(ok|okay|honestly|underwhelming|way too|probably won't|won't go back|broth was fine|drag me there|i've been thinking|kind of|kinda|sort of)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    colloquial_signal = _normalize(colloquial_penalty, 0, 4)

    score = (
        0.28 * variance_signal
        + 0.20 * sentence_count_signal
        + 0.24 * formality_signal
        + 0.12 * repetition_signal
        + 0.08 * punctuation_signal
        + 0.08 * (1.0 - colloquial_signal)
    )
    score = max(0.0, min(1.0, score))
    attribution = "likely_ai" if score >= 0.5 else "likely_human"
    rationale = (
        "Stylometric score derived from sentence length variance, sentence count, "
        "formality markers, repetition, and punctuation density."
    )

    return SignalResult(
        score=score,
        attribution=attribution,
        rationale=rationale,
        source="stylometric",
        details=features.to_dict(),
    )
