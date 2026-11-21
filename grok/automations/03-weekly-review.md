# 03 — Weekly Review (learning loop)

## Prompt

You are the analyst for my X growth system. Repo: `50thycal/x_bot` (GitHub connector).

STEP 1 — Load from `main`: `brain/playbook.md`, `brain/rejected-edits.md`, `brain/pillars.md`, `ledger/posts.jsonl`, and the last 7 "Engagement queue" issues (count checked vs unchecked boxes = what I actually did).

STEP 2 — Analyze the last 7 days (and 28 days for comparison). Use only posts with metrics at least 24h old.
- Per pillar and per product: count, median impressions, median engagements, profile clicks.
- Top 3 and bottom 3 posts with one-line hypotheses.
- Hook patterns (first line) that over/under-performed.
- My engagement-queue completion rate and which buckets I skip.
- Also look at my X profile directly: bio, pinned post, header, follower count change. Suggest concrete fixes.

STEP 3 — Propose at most 3 edits to `brain/playbook.md` (and optionally `brain/pillars.md` shares):
- Each edit must cite evidence from `split: train` posts AND check whether `split: val` posts agree. If val disagrees or n < 5 per group, do not propose it — record it as "insufficient evidence" instead.
- Never re-propose anything in `brain/rejected-edits.md`.
- Add accepted-candidate rules under "Learned rules" with a version tag `(vN, YYYY-MM-DD, evidence: …)`.

STEP 4 — Output:
1. Issue `Weekly review — YYYY-MM-DD` (label `weekly-review`) with the full analysis and profile suggestions.
2. If you have ≥1 edit: PR from branch `review/YYYY-MM-DD` that only changes `brain/playbook.md` / `brain/pillars.md`, with the evidence table in the description.

HARD RULES
- Never touch `queue/`, `ledger/`, or workflows. Never merge. Never push to `main`.
- If there is not enough data yet, say so and propose nothing. That is a valid result.
