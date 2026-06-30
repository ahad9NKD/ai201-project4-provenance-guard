# Provenance Guard

Backend system for AI content provenance classification, transparency labels, appeals, rate limiting, and audit logging.

## What It Does

Provenance Guard receives a text submission, runs two distinct detection signals, combines them into a calibrated confidence score, and returns a transparency label that a platform could show to readers. It also supports creator appeals, rate limiting, and a structured audit log so every classification and dispute is traceable.

## Architecture

The request path is:

1. `POST /submit` receives text plus `creator_id`.
2. Flask validates the payload and rate limits the request.
3. Signal 1 runs a Groq-backed language-model assessment, with a local fallback when the API is unreachable in this environment.
4. Signal 2 runs stylometric heuristics in pure Python.
5. The scorer combines both signals into a calibrated confidence score and chooses the reader-facing label text.
6. The audit log stores the full decision record.
7. The API returns `content_id`, attribution, confidence, labels, and both signal outputs.
8. `POST /appeal` marks a submission `under_review`, stores creator reasoning, and appends the appeal to the log.

That design keeps submission, classification, labeling, and dispute handling separate while still sharing one persistent record of what happened.

## Detection Signals

### Signal 1: Groq-backed semantic assessment

This signal asks an LLM to judge whether the text reads more human or more AI-generated. It captures global coherence, discourse style, and the kind of polished sameness that models often produce.

Why this signal:

- It sees semantic and stylistic cues together instead of only counting surface statistics.
- It is useful for polished prose where simple heuristics may be unsure.

Blind spot:

- It is vulnerable to short texts, deliberate style mimicry, and network/API failures.
- In this project’s environment, the live Groq call is not reachable, so the code falls back to a local heuristic. The API path is still implemented and will be used when the request can reach Groq.

What I would change in a real deployment:

- Add a labeled validation set and calibrate the LLM score on actual platform data.
- Retry or queue failed API calls instead of immediately falling back.
- Log the model output separately from the fallback path for observability.

### Signal 2: Stylometric heuristics

This signal measures sentence-length variance, type-token ratio, punctuation density, repetition, sentence count, and formality markers. AI writing often looks more regular, while human writing tends to have more rhythm and messiness.

Why this signal:

- It is cheap, deterministic, and easy to inspect.
- It catches structural patterns that a semantic judge might miss.

Blind spot:

- It can misread intentionally formal human prose as AI-like.
- It cannot understand meaning, author intent, or genre conventions.

What I would change in a real deployment:

- Fit the heuristic weights against real examples from the target platform.
- Break the signal down into per-genre profiles so poems, essays, and blog posts are scored differently.

## Confidence Scoring

The score is intentionally an AI-likeness score from `0.0` to `1.0`:

- `0.0` means strongly human-like.
- `0.5` means the system cannot decide.
- `1.0` means strongly AI-like.

The two signal scores are combined as:

```text
base = 0.6 * groq_score + 0.4 * stylometric_score
disagreement = abs(groq_score - stylometric_score)
calibrated = 0.5 + (base - 0.5) * (1 - 0.5 * disagreement)
```

That formula does two things:

- It gives the LLM signal slightly more influence than the heuristic.
- It reduces confidence when the signals disagree, which helps avoid overconfident false positives.

Thresholds:

- `0.75` and above: likely AI
- `0.25` and below: likely human
- between `0.25` and `0.75`: uncertain

Why this approach:

- A binary flip at `0.5` would make the system sound more certain than it really is.
- The middle band is important because false positives are worse than false negatives for a writing platform.

Two concrete examples from testing:

- Clearly AI-like sample: confidence `0.7812`, label `high_confidence_ai`
- Clearly human sample: confidence `0.1316`, label `high_confidence_human`

Two borderline examples from the same test set:

- Formal human writing: confidence `0.6957`, label `uncertain`
- Lightly edited AI output: confidence `0.4313`, label `uncertain`

If I were deploying this for real, I would calibrate the score against a labeled dataset and tune the thresholds per content type.

## Transparency Labels

The exact user-facing labels are:

- High-confidence AI: `"This text is likely AI-generated. We are fairly confident because multiple signals point in the same direction."`
- High-confidence human: `"This text is likely human-written. We are fairly confident because multiple signals point in the same direction."`
- Uncertain: `"We cannot confidently tell whether this text was written by a human or AI. The signals are mixed or weak."`

The label varies by confidence band, so it is not a constant response.

## Appeals Workflow

- Who can appeal: the original creator of the content.
- What they provide: `content_id` and `creator_reasoning`.
- What happens on appeal:
  - The stored submission is updated to `status: "under_review"`.
  - The original classification decision stays in the audit trail.
  - The appeal reasoning is added to the audit log.

What a human reviewer would see:

- The original text and creator id.
- The original attribution and confidence score.
- Both signal scores.
- The creator’s appeal reasoning.
- The current status: `under_review`.

## Rate Limiting

The submission endpoint uses Flask-Limiter with:

- `10 per minute`
- `100 per day`

Why those numbers:

- A real writer may submit a few drafts or revisions in a short session.
- A flood of automated submissions should be blocked quickly.
- `10 per minute` is high enough for normal usage and low enough to stop a script from spamming the endpoint.
- `100 per day` gives a second layer of protection against repeated abuse.

Evidence from local testing:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

## Audit Log

The log is structured JSON, stored as JSON Lines on disk. Each submission entry includes:

- `timestamp`
- `content_id`
- `creator_id`
- `attribution`
- `confidence`
- `combined_score`
- `signal_1_score`
- `signal_2_score`
- `status`
- `appeal_filed`

Appeal entries add:

- `appeal_id`
- `appeal_reasoning`
- `status: "under_review"`

Sample log entry:

```json
{
  "appeal_filed": true,
  "appeal_id": "51245721-5b86-4fc6-9880-4d5e33331324",
  "appeal_reasoning": "I wrote this myself and want a human review.",
  "attribution": "uncertain",
  "confidence": 0.3852,
  "content_id": "4efe753e-ff13-4a7d-a013-90648b9ca232",
  "creator_id": "appeal-user",
  "signal_1_score": 0.35,
  "signal_2_score": 0.4267,
  "status": "under_review",
  "timestamp": "2026-06-29T04:13:58.583764Z"
}
```

## Known Limitations

This system will likely struggle with formal human writing that uses polished, evenly structured sentences. The stylometric signal treats low variance and high formality as AI-like traits, so an academic paragraph or legal-style prose can land in the uncertain band even when a human wrote it.

Another weak spot is very short text. With only one sentence or a few words, both signals have too little information to distinguish style reliably.

These limitations come directly from the signals:

- Stylometric heuristics confuse structure with authorship style.
- The LLM signal is less useful when there is not enough content to read deeply.

## Spec Reflection

One way the spec helped:

- It forced me to design the architecture before coding, which made the API contract, labels, and audit trail much more consistent.

One way the implementation diverged:

- The spec expected a live Groq signal in every environment, but the local environment could not reach the Groq API reliably. To keep the system usable, I added a fallback heuristic inside the Groq signal path. That keeps the endpoint working while preserving the same interface.

## AI Usage

I used AI as a drafting and review aid, not as a blind source of truth.

Specific instance 1:

- I asked an AI tool to outline the architecture narrative and the API surface from `planning.md`.
- It produced a strong first draft with the submission flow, appeal flow, and diagram structure.
- I revised it to add concrete thresholds, exact label text, and the milestone-specific AI Tool Plan.

Specific instance 2:

- I asked an AI tool to help shape the first signal and confidence scoring logic.
- It produced a plausible scoring path, but I overrode the thresholds and combined-score behavior to preserve a meaningful uncertain band and to match the project spec.

Specific instance 3:

- I asked an AI tool to help think through the appeal workflow and audit logging.
- I kept the overall structure but revised the log schema so it explicitly records `appeal_filed`, `appeal_reasoning`, and the original decision together.

## Portfolio Walkthrough

Short walkthrough reference:

- [Demo video link](./demo_video.md)
- Show `POST /submit` with a sample text.
- Show `GET /log` with the structured audit entry.
- Show `POST /appeal` and the `under_review` status.
- Briefly mention the two signals, the uncertainty band, and the rate limit.

## Project Files

- [planning.md](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/planning.md)
- [demo_video.md](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/demo_video.md)
- [app.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/app.py)
- [scoring.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/scoring.py)
- [signal_one.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/signal_one.py)
- [signal_two.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/signal_two.py)
- [appeals.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/appeals.py)
- [storage.py](/Users/abdoulahaddiouck/ai201-project4-provenance-guard/storage.py)
