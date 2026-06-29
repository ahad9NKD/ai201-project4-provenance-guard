from __future__ import annotations

import uuid

from storage import append_audit_entry, get_submission, store_appeal, update_submission, utc_now


def submit_appeal(content_id: str, creator_reasoning: str) -> dict[str, object] | None:
    submission = get_submission(content_id)
    if submission is None:
        return None

    appeal_id = str(uuid.uuid4())
    timestamp = utc_now()
    appeal_record = {
        "appeal_id": appeal_id,
        "content_id": content_id,
        "creator_id": submission.get("creator_id"),
        "creator_reasoning": creator_reasoning,
        "original_attribution": submission.get("attribution"),
        "original_confidence": submission.get("confidence"),
        "timestamp": timestamp,
        "status": "under_review",
        "appeal_filed": True,
    }
    store_appeal(appeal_record)
    update_submission(
        content_id,
        {
            "status": "under_review",
            "appeal_filed": True,
            "appeal_id": appeal_id,
            "appeal_reasoning": creator_reasoning,
        },
    )
    append_audit_entry(
        {
            "appeal_id": appeal_id,
            "content_id": content_id,
            "creator_id": submission.get("creator_id"),
            "timestamp": timestamp,
            "attribution": submission.get("attribution"),
            "confidence": submission.get("confidence"),
            "signal_1_score": submission.get("signal_1_score"),
            "signal_2_score": submission.get("signal_2_score"),
            "status": "under_review",
            "appeal_reasoning": creator_reasoning,
            "appeal_filed": True,
        }
    )

    return {
        "appeal_id": appeal_id,
        "content_id": content_id,
        "status": "under_review",
        "appeal_reasoning": creator_reasoning,
        "timestamp": timestamp,
    }
