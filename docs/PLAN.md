# x_bot build plan

**Goal:** grow an X audience of people who would buy your games (mobile + board),
with Grok doing the thinking, GitHub holding the memory, and you spending
~15 minutes a day on the parts X requires a human for.

See [RESEARCH.md](RESEARCH.md) for the repos this merges and the rules that
constrain it.

## 1. Architecture

```
            ┌──────────────────────── GitHub repo (this) ─────────────────────────┐
            │  brain/      who you are, voice, products, targets, playbook        │
            │  queue/      drafted originals (on main = approved)                 │
            │  ledger/     posts.jsonl (what shipped + metrics), engagement logs  │
            └───────▲───────────────────────▲───────────────────────┬────────────┘
                    │ PRs / issues          │ merge = approve       │ cron
 ┌──────────────────┴─────────┐   ┌─────────┴─────────┐   ┌─────────▼──────────────┐
 │ Grok Automations (no cost) │   │ You (GitHub app)  │   │ GitHub Actions         │
 │ • Daily Scout  (X search)  │   │ • merge draft PRs │   │ • publish.yml  /30 min │
 │ • Daily Writer (drafts PR) │   │ • work the daily  │   │ • metrics.yml  /6 h    │
 │ • Weekly Review (learning) │   │   engagement issue│   │ • validate.yml on PR   │
 └──────────────┬─────────────┘   └─────────┬─────────┘   └─────────┬──────────────┘
                │ reads X natively          │ replies/likes/follows │ X API (pay-per-use)
                ▼                           ▼                       ▼
                                  ┌──────────── X ────────────┐
```

Three actors, each doing only what it is allowed and good at:

| Actor | Does | Never does |
|---|---|---|
| **Grok** | Searches X (free, native), scores opportunities, drafts posts/replies, opens PRs + issues, proposes playbook edits | Push to `main`, post to X, follow instructions found inside X posts |
| **You** | Merge/close draft PRs, tap the reply/like/follow links in the daily issue, fill `brain/` | Write posts from scratch (unless you want to) |
| **GitHub Actions** | Post approved originals when due, pull metrics into the ledger, validate drafts | Like, follow, reply, or post anything not on `main` |

## 2. The merged feature set

| Feature | Taken from | How it works here |
|---|---|---|
| Brain files as source of truth | wingman-x | `brain/*.md`; every Grok prompt starts by reading them |
| Provenance + "why" on every draft | wingman-x | Draft front-matter `why:` and `brain_refs:`; queue issue shows match reason |
| Researcher → Writer → Scheduler → Publisher | twitter-agent | Scout automation → Writer automation (assigns `scheduled_at` slots ≥90 min apart) → `publish.yml` |
| Dedup log before action | twitter-agent | Publisher appends to `ledger/posts.jsonl` keyed by draft `id`; reruns skip |
| Caps + cooldowns | twitter-agent | Per-day caps in `brain/playbook.md`; recommended follows have a 14-day per-author cooldown |
| Gold filter | grokbot-x | `views / author_followers ≥ 12`, `< 400` replies, < 6 h old |
| Two lanes | grokbot-x | Originals: auto-post after PR merge. Replies/likes/follows: human taps from the daily issue |
| Trajectory log + gated learning | grokbot-x | `ledger/posts.jsonl` with frozen `features` + refreshed `metrics`; Weekly Review proposes ≤3 playbook edits as a PR with evidence; you merge only if the numbers back it |

## 3. Daily / weekly loop

| When | Who | What |
|---|---|---|
| 08:00 daily | Grok — **Daily Scout** | Search X (last 24 h) → open issue *"Engagement queue — DATE"*: 5–10 reply opportunities (link, gold ratio, why, drafted reply), 3–5 accounts worth following, customer-intent posts (people asking for games like yours) |
| 08:00–08:15 | **You** | Work the issue from your phone: open link, paste/edit reply, like, follow. Tick checkboxes. |
| 20:00 daily | Grok — **Daily Writer** | Read brain + ledger + yesterday's issue → open PR adding 2–3 originals for tomorrow in `queue/` with slots |
| Evening | **You** | Merge the PR (edit inline if needed) or close it |
| Every 30 min | Action — **publish** | Post any merged draft whose `scheduled_at` has passed and isn't in the ledger |
| Every 6 h | Action — **metrics** | Refresh impressions/likes/replies/bookmarks/profile clicks for posts < 7 days old |
| Sunday | Grok — **Weekly Review** | Per-pillar/product performance, best + worst posts, account audit (bio, pinned post, header), propose ≤3 playbook edits as a PR |

## 4. Audience → customer funnel

1. **Attention:** gold replies in the niches your buyers live in (indie game dev, cozy games, tabletop/board games, Kickstarter backers) — this is the main growth engine on a cold account.
2. **Trust:** originals across pillars — devlogs with GIFs/photos, design decisions, playtest results, honest numbers.
3. **Capture:** profile → pinned post → one link in bio (waitlist / Kickstarter pre-launch page / TestFlight or Play beta). UTM-tagged so you can see which product pulls.
4. **Intent lane:** Scout flags posts where someone is *asking* for what you make ("looking for a 2-player board game…", "cozy mobile game recs?"). You reply personally — these are your highest-value interactions.
5. **Measure:** Weekly Review reports followers gained, profile clicks, link clicks per product. Those numbers drive playbook edits.

## 5. Build phases

### Phase 0 — Brain + Grok prompts (this PR, no code, no cost)
- [x] Research and plan (`docs/`)
- [x] `brain/` templates
- [x] Grok automation prompts in `grok/automations/`
- [x] Handle set (@50th_ETH), pre-launch pillar mix set
- [ ] **You:** fill `brain/brand-bible.md`, `voice.md`, `products/*.md`, `targets.md`
- [ ] **You:** create the three automations at grok.com/automations from the prompt files
- [ ] **Validation test:** run Daily Scout once manually and confirm Grok can (a) search X, (b) open an issue in this repo from inside an automation. If (b) fails → use Fallback B below.

### Phase 1 — Publisher ✅ built
- `publisher/publish.py`: parses `queue/*.md`, posts due drafts via X API v2 (OAuth 1.0a, stdlib only), threads as self-replies, appends to `ledger/posts.jsonl` immediately after each post (no double posts on crash), archives to `queue/posted/`.
- Approval: a draft is only posted if its last commit belongs to a PR merged into `main` (checked via the GitHub API). Direct pushes to `main` are blocked.
- Caps: ≤3/day, ≥90 min apart, 1 per run, skip if > 3 h late (no catch-up bursts). Tunable in `publisher/config.json`.
- `publish.yml` runs at :07 and :37 each hour + manual, `concurrency: ledger-writer` so runs never overlap.
- `validate.yml` on every PR: unit tests + draft rules (≤280 weighted chars, no URLs, no TODOs, valid pillar/product, spacing, daily cap).
- **Dry run unless repo variable `PUBLISH_ENABLED=true`.** Setup steps: [SETUP.md](SETUP.md).

### Phase 2 — Metrics + ledger ✅ built
- `publisher/metrics.py` (`metrics.yml`, every 3 h) refreshes impressions, likes, replies, reposts, quotes, bookmarks, profile clicks at +1h/+6h/+24h/+72h/+7d checkpoints. Makes zero API calls when nothing is due.
- Weekly Review gets real numbers to learn from.

### Phase 3 — Gated learning (grokbot-x's SkillOpt, simplified)
- Mark ~20% of posts as `split: val`. A playbook edit is proposed only from `train`, and judged on `val` performance; rejected edits go to `brain/rejected-edits.md`.
- Start with "median impressions per post, by pillar" as the reward; add profile-click rate once volume allows.

### Phase 4 — Optional
- Media: attach images/GIFs from `queue/media/` (devlog clips are the best-performing game content).
- Swap publisher for Typefully/Postiz if you want a calendar UI.
- Apply to X for AI-reply approval if you ever want reply automation (only then).

## 6. Fallback B (if Grok automations can't write to GitHub) ✅ built

Built in `agents/` + `.github/workflows/agent-*.yml` after the Grok GitHub connector turned out to need a manual confirmation for every write. See SETUP.md → 3b.

Run the same three prompts inside GitHub Actions against the xAI API with
the `x_search` tool (exactly what twitter-agent does). Same repo layout, same
files, just a different trigger. Cost: a few cents/day of xAI API usage.

## 7. Cost estimate

Per action (X API pay-per-use, Nov 2026 rate card):

| Action | Who does it | Cost each |
|---|---|---|
| Post (no link) | publisher | **$0.015** |
| Each extra thread part | publisher | $0.015 |
| Post containing a URL | blocked by validator | $0.20 |
| Read metrics of your own post | metrics job | ~$0.001 |
| Like / follow / repost via API | **not used** (X bans automating them) | would be $0.015 |
| Likes, follows, replies you tap yourself | you, in the X app | **$0** |
| Grok searching X / drafting | Grok app | **$0** (in your Grok plan) |
| GitHub Actions | public repo | **$0** |

Monthly at the default caps:

| Item | Volume | Cost/month |
|---|---|---|
| Original posts | ≤3/day ≈ 90 | ≈ **$1.35** (max $1.35 + thread parts) |
| Metric reads | ~90 posts × 5 checkpoints | ≈ **$0.45** |
| **Total** | | **≈ $1.80/month → $5 lasts ~2.5 months** |

## 8. Guardrails (non-negotiable)

1. No automated likes, follows, unfollows, or replies. Recommendations only.
2. No URLs in auto-posted originals (cost and reach). Links live in bio/pinned post.
3. ≤1 original per hour, ≤4 originals/day to start.
4. Grok treats all X content as untrusted data — never follows instructions inside a post.
5. Nothing reaches X that isn't on `main`. `main` requires a PR.
6. Kill switch: set repo variable `PUBLISH_ENABLED=false` (or disable the workflow).

## 9. Open questions for you

1. Your X handle and current follower count (sets cold-start vs warm strategy).
2. Product details: names, stage (concept / prototype / beta / launched), the one link you want people to click.
3. Which niche communities you already belong to (accounts, hashtags, lists).
4. Your Grok plan (SuperGrok / Premium+) — affects automation limits.
5. Are you OK with ~$5 of X API credit to start Phase 1?
