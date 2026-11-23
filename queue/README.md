# queue/

Drafted originals waiting to post. **A file on `main` is approved.** Grok adds files via PR; you approve by merging.

- Format: see `grok/automations/02-daily-writer.md`.
- The Phase 1 publisher posts any file whose `scheduled_at` has passed and whose `id` isn't in `ledger/posts.jsonl`, then moves it to `queue/posted/`.
- To cancel a post: delete the file (or close the PR before merging). To pause one: add `hold: true`.
- Edit drafts **inside the PR before merging**. A direct edit on `main` makes the draft unapproved (its last commit is no longer from a merged PR), and it will be blocked until it comes back through a PR.
- Video: put an mp4 (H.264, ≤ 512 MB, ≤ 140 s) at `queue/media/<id>.mp4` in the same PR (or set `media: queue/media/other.mp4` in the front matter). It is attached to the first part. The file must be merged with the draft; `validate` checks it exists and is a sane size.
