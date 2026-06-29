from __future__ import annotations

import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from appeals import submit_appeal
from signal_one import run_first_signal
from signal_two import run_second_signal
from scoring import combine_signals
from storage import append_audit_entry, get_audit_entries, store_submission


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_app() -> Flask:
    app = Flask(__name__)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )

    @app.post("/submit")
    @limiter.limit("10 per minute;100 per day")
    def submit() -> tuple[dict, int]:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        creator_id = payload.get("creator_id")

        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "text is required"}), 400
        if not isinstance(creator_id, str) or not creator_id.strip():
            return jsonify({"error": "creator_id is required"}), 400

        content_id = str(uuid.uuid4())
        signal_one_result = run_first_signal(text)
        signal_two_result = run_second_signal(text)
        combined_result = combine_signals(signal_one_result, signal_two_result)
        timestamp = utc_now()

        record = {
            "content_id": content_id,
            "creator_id": creator_id,
            "timestamp": timestamp,
            "attribution": combined_result.attribution,
            "confidence": round(combined_result.confidence, 4),
            "combined_score": round(combined_result.combined_score, 4),
            "signal_1_score": round(float(signal_one_result.score), 4),
            "signal_2_score": round(float(signal_two_result.score), 4),
            "signal_1_source": signal_one_result.source,
            "signal_2_source": signal_two_result.source,
            "status": "classified",
            "label": combined_result.label,
            "appeal_filed": False,
        }
        store_submission(record)
        append_audit_entry(record)

        return (
            jsonify(
                {
                    "content_id": content_id,
                    "creator_id": creator_id,
                    "attribution": combined_result.attribution,
                    "confidence": round(combined_result.confidence, 4),
                    "combined_score": round(combined_result.combined_score, 4),
                    "label": combined_result.label,
                    "timestamp": timestamp,
                    "signal_1": signal_one_result.to_dict(),
                    "signal_2": signal_two_result.to_dict(),
                    "label_category": combined_result.label_category,
                    "appeal_filed": False,
                }
            ),
            200,
        )

    @app.post("/appeal")
    def appeal() -> tuple[dict, int]:
        payload = request.get_json(silent=True) or {}
        content_id = payload.get("content_id")
        creator_reasoning = payload.get("creator_reasoning")

        if not isinstance(content_id, str) or not content_id.strip():
            return jsonify({"error": "content_id is required"}), 400
        if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
            return jsonify({"error": "creator_reasoning is required"}), 400

        result = submit_appeal(content_id.strip(), creator_reasoning.strip())
        if result is None:
            return jsonify({"error": "content_id not found"}), 404

        return jsonify(result), 200

    @app.get("/log")
    def log() -> tuple[dict, int]:
        return jsonify({"entries": get_audit_entries()}), 200

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return jsonify({"status": "ok"}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
