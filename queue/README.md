# queue/

Drafted originals waiting to post. **A file on `main` is approved.** Grok adds files via PR; you approve by merging.

- Format: see `grok/automations/02-daily-writer.md`.
- The Phase 1 publisher posts any file whose `scheduled_at` has passed and whose `id` isn't in `ledger/posts.jsonl`, then moves it to `queue/posted/`.
- To cancel a post: delete the file (or close the PR before merging).
- Media (Phase 4): `queue/media/<id>.(png|gif|mp4)`.
