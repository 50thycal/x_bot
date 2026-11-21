# Research: open-source X growth agents (Nov 2026)

Goal: find existing GitHub projects that automate growing an X audience with an
LLM, pick the three with the best *simple* ideas, and merge them into one
system that Grok (with its GitHub connector + Automations) can run.

## Hard constraints discovered during research

These shape everything else, so they come first.

| Constraint | Source | Consequence for us |
|---|---|---|
| X bans **automated likes** (incl. by keyword/hashtag/schedule, incl. browser extensions) | [X automation rules](https://help.x.com/en/rules-and-policies/x-automation), [Developer Agreement](https://docs.x.com/developer-guidelines) | Likes stay manual. The bot only *recommends* them. |
| X bans **automated follow / unfollow** | [X automation rules](https://help.x.com/en/rules-and-policies/x-automation) | Follows stay manual. The bot only *recommends* them. |
| **Automated replies based on keyword search are not permitted**; AI apps that generate *and post* replies need prior X approval | [X automation rules](https://help.x.com/en/rules-and-policies/x-automation), [Developer Agreement](https://docs.x.com/developer-guidelines) | Replies are drafted by Grok, posted by a human tap. |
| Scripting x.com in a browser is banned | X automation rules | No Playwright/cookie bots (rules out XActions, MiloAgent-style tooling). |
| Penalty is suspension | Developer Agreement | Losing the account = losing the audience. Compliance is a growth requirement, not a nicety. |
| X API is **pay-per-use**: ~$0.015 per post, ~$0.20 per post containing a URL, ~$0.001 per read of your own data | [docs.x.com pricing](https://docs.x.com/x-api/getting-started/pricing.md), [opentweet](https://opentweet.io/x-api-pricing), [bundle.social](https://bundle.social/blog/x-api-pricing-2026-costs-limits) | Posting our own originals is pennies. Never put URLs in auto-posts (13× cost); keep links in bio / pinned post. |
| Grok **cannot post to X** but has native real-time X search, a GitHub connector, and scheduled Automations | Grok's own capability statement; [xAI Automations](https://x.ai/news/grok-automations); [xAI connectors](https://x.ai/blog/grok-connectors) | Grok = researcher + writer (free X reads). GitHub = shared memory + approval queue. GitHub Actions = the only thing that touches the X API. |

## Candidates surveyed

| Repo | ★ | Stack | Core idea | Verdict |
|---|---|---|---|---|
| [YannisKiefer/grokbot-x](https://github.com/YannisKiefer/grokbot-x) | 84 | Python stdlib | Grok skills; scout "gold" posts (views ≫ followers); drafts in your voice; originals auto-publish, replies human-approved; logs every post; nightly gate keeps playbook edits only if metrics improve | **PICK #1** |
| [arvindrk/twitter-agent](https://github.com/arvindrk/twitter-agent) | 5 | Bun/Hono/Neon | Grok-powered 3-loop pipeline: researcher → writer → scheduler (slots ≥90 min apart) → cron publisher; engagement loop with per-run caps, dedup log, cooldowns | **PICK #2** (pipeline + caps; *not* its auto-like/follow) |
| [stone16/wingman-x](https://github.com/stone16/wingman-x) | 1 | TS, Chrome ext | Knowledge base (`tone.md` + `library/*.md`) is the voice source; every candidate carries *match reason* + *which KB files it cited*; one-click fill, human presses Tweet | **PICK #3** (KB + provenance + queue UX) |
| SoCloseSociety/MiloAgent | 46 | Python | Self-learning Reddit/X agent, A/B tests, prompt evolution | Rejected: multi-account rotation + ban evasion = suspension risk |
| nirholas/XActions | 662 | JS | Scrapers + MCP server with approval-gated writes | Rejected: scripts x.com without the API |
| per-simmons/ai-reply-guy-opensource | 2 | Next.js | Reply dashboard, Chrome debugger keystrokes | Rejected: keystroke injection into x.com; heavy infra |
| cameronking4/ReplyGuy-clone | 121 | Next.js | Keyword-scrape + promo replies | Rejected: mostly a SaaS template; keyword auto-reply is banned |
| gitroomhq/postiz-app | 42k | TS | Full social scheduler | Too heavy for v1; possible future publisher swap |
| d60/twikit, x-tweet-fetcher | 4.8k / 1k | Python | Unofficial read clients | Not needed: Grok reads X natively |

## What we take from each pick

### #1 grokbot-x → the *learning loop* and the *two lanes*
- **Gold filter**: `viral_ratio = views / author_followers`, keep ≥12; skip threads with 400+ replies (you'll be invisible).
- **Two lanes never mixed**: originals can publish automatically; replies always need a human click.
- **Trajectory log**: one JSON line per shipped post with frozen features + metrics refreshed at +1h/+6h/+24h.
- **Gated playbook**: `playbook.md` is the trainable state; an edit is kept only if held-out numbers improve. Rejected edits are logged so the loop doesn't retry them.
- **Human cadence**: max 1 original/hour, no bursts, start at 5–15 quality ships/day (most of them manual replies on a cold account).

### #2 twitter-agent → the *pipeline shape* and *guardrails*
- Researcher → Writer → Scheduler → Publisher as separate stages with structured output.
- Named time slots, ≥90 min apart; publisher runs on a cron and only posts what's due.
- Dedup / claim log written **before** acting so retries are no-ops.
- Hard per-run caps and per-author cooldowns (we apply these to *recommendations*, not automated actions).

### #3 wingman-x → the *brain* and the *review UX*
- Voice + expertise live in plain Markdown files the agent must read before drafting.
- Every draft carries **why** (match reason) and **provenance** (which brain files it used) so you can trust-but-verify in seconds.
- Candidate queue → open link → draft is ready → *you* press post. No auto-posting of replies, ever.
