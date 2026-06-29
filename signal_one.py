from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

load_dotenv()

@dataclass
class SignalResult:
    score: float
    attribution: str
    rationale: str
    source: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "score": round(float(self.score), 4),
            "attribution": self.attribution,
            "rationale": self.rationale,
            "source": self.source,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload


def _fallback_score(text: str, reason: str = "GROQ_API_KEY is unavailable") -> SignalResult:
    lowered = text.lower()
    words = re.findall(r"\b\w+\b", lowered)
    word_count = max(1, len(words))
    sentence_count = max(1, len(re.findall(r"[.!?]+", text)))
    avg_sentence_length = word_count / sentence_count
    first_person_count = len(re.findall(r"\b(i|me|my|we|our|us)\b", lowered))
    contraction_count = len(re.findall(r"\b\w+'(?:t|s|re|ve|ll|d|m)\b", lowered))
    colloquial_markers = len(
        re.findall(
            r"\b(ok|okay|honestly|basically|just|kind of|kinda|sort of|lol|ugh|gonna|wanna|probably|WAY)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    formal_markers = len(
        re.findall(
            r"\b(important to note|furthermore|equally essential|stakeholders|collaborate|responsible deployment|ethical implications|numerous|various sectors|transformation|fundamental tension|prolonged low interest rates|price stability)\b",
            lowered,
        )
    )
    abstract_words = len(
        re.findall(
            r"\b(ethical|implications|benefits|stakeholders|collaborate|responsible|deployment|transformative|paradigm|essential|fundamental|valuations|stability|inflation|monetary|policy|consequences|prolonged)\b",
            lowered,
        )
    )
    punctuation_density = len(re.findall(r"[,:;()\-\"]", text)) / max(1, len(text))

    score = 0.35
    score += min(0.3, formal_markers * 0.08 + abstract_words * 0.025)
    if formal_markers >= 3:
        score += 0.08
    score += min(0.15, max(0.0, (avg_sentence_length - 12) / 40))
    score += min(0.1, punctuation_density * 1.2)
    score -= min(0.2, first_person_count / max(1, word_count) * 2.5)
    score -= min(0.15, contraction_count / max(1, word_count) * 3.0)
    score -= min(0.2, colloquial_markers * 0.06)
    score = max(0.0, min(1.0, score))
    attribution = "likely_ai" if score >= 0.5 else "likely_human"
    rationale = (
        f"Fallback heuristic used because {reason}; "
        f"word_count={word_count}, sentence_count={sentence_count}, avg_sentence_length={avg_sentence_length:.1f}."
    )
    return SignalResult(score=score, attribution=attribution, rationale=rationale, source="fallback")


def _parse_structured_response(content: str) -> SignalResult:
    data = json.loads(content)
    score = float(data.get("score", 0.5))
    attribution = str(data.get("attribution", "uncertain"))
    rationale = str(data.get("rationale", "")).strip()
    if attribution not in {"likely_ai", "likely_human", "uncertain"}:
        attribution = "uncertain"
    return SignalResult(score=score, attribution=attribution, rationale=rationale, source="groq")


def run_first_signal(text: str) -> SignalResult:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _fallback_score(text)

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You judge whether a text is likely human-written or AI-generated. "
                        "Return strict JSON with keys score, attribution, and rationale. "
                        "score must be a number from 0 to 1 where 1 means strongly AI-generated. "
                        "attribution must be one of likely_ai, likely_human, or uncertain."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Analyze this text:\n\n{text}",
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return _parse_structured_response(content)
    except (json.JSONDecodeError, ValueError, TypeError, Exception) as error:
        return _fallback_score(text, reason=f"GROQ request failed ({error.__class__.__name__})")
