# ledger/

`posts.jsonl` — one line per shipped post, written by the publisher, metrics refreshed by `metrics.yml`:

```json
{"id":"2026-11-22-cut-rules","x_id":"1860000000000000000","posted_at":"2026-11-22T14:00:05Z","type":"original","pillar":"devlog","product":"board-game","split":"train","text":"...","features":{"hook_words":9,"has_media":false,"hour_utc":14},"metrics":{"impressions":0,"likes":0,"replies":0,"reposts":0,"bookmarks":0,"profile_clicks":0,"refreshed_at":null}}
```

`features` are frozen at ship time; only `metrics` change later (grokbot-x trajectory rule).
