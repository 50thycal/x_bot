# Setup (about 30 minutes)

Do these in order. Nothing posts until step 4.

## 1. X developer app (keys for posting)

1. Go to **developer.x.com** → sign in as **@50th_ETH** → open the Developer Console.
2. Create a Project + App (any name, e.g. `x-bot-publisher`).
3. App → **User authentication settings** → Set up:
   - App permissions: **Read and write**
   - Type of App: **Web App, Automated App or Bot**
   - Callback URI: `https://localhost` · Website URL: your X profile URL
4. App → **Keys and tokens**:
   - **API Key and Secret** (a.k.a. consumer key) → copy both.
   - **Access Token and Secret** → *Generate* (or *Regenerate* if you created them before step 3 — tokens made before "Read and write" are read-only) → copy both. They must say "Created with Read and Write permissions".
5. Billing → buy **$5** of pay-per-use credit.

## 2. GitHub secrets

Repo → **Settings → Secrets and variables → Actions → Secrets → New repository secret**:

| Name | Value |
|---|---|
| `X_API_KEY` | API Key |
| `X_API_SECRET` | API Key Secret |
| `X_ACCESS_TOKEN` | Access Token |
| `X_ACCESS_TOKEN_SECRET` | Access Token Secret |

Never paste these into an issue, PR, chat, or file. The repo is **public**.

## 3. Grok automations

Follow [`grok/automations/README.md`](../grok/automations/README.md). Fill the `TODO`s in `brain/` first (handle and pre-launch stage are already set).

## 3b. Fallback B: run the prompts in GitHub Actions (active)

Grok's own automations can search X, but their GitHub connector stops at a manual
confirmation form, so they can't create issues or PRs unattended. Fallback B runs the
same three jobs in GitHub Actions against the xAI API. Grok only gets `x_search`; the
workflow (not Grok) creates the issue / opens the PR, so Grok has no GitHub access.

| Workflow | When (UTC) | Output |
|---|---|---|
| `agent-scout` | every other day 14:03 (8:03 am CST) | issue "Engagement queue — DATE" |
| `agent-writer` | daily 02:03 (8:03 pm CST) | PR "Drafts for DATE" (merge = approve) |
| `agent-review` | Mon 00:13 (Sun 6:13 pm CST) | issue "Weekly review — DATE" (+ playbook PR if evidence) |

Setup:
1. console.x.ai → API Keys → create a key → repo secret **`XAI_API_KEY`** (paste it yourself, never in chat/files).
2. Repo → Settings → Actions → General → Workflow permissions → tick
   **Allow GitHub Actions to create and approve pull requests** (needed for the writer/review PRs).
3. Optional repo variables: `XAI_MODEL` (default `grok-4.7`), `XAI_MAX_TURNS` (Weekly Review, default 8), `AGENTS_ENABLED=false` to pause all three.
   Scout has its own knobs: `XAI_SCOUT_MAX_TURNS` (default 3) and `XAI_SCOUT_MODEL` (defaults to `XAI_MODEL`; set a cheaper Grok model from console.x.ai → Models to cut cost further).
   Cost history: the first Scout runs (8 turns, 48–66 searches, ~600k input tokens) cost **$2.07–2.35**. Almost all of it is input tokens,
   because every turn re-reads the context plus all search results. Scout now caps itself at 12 searches / 3 turns and runs every other day.
4. Actions → **agent-scout** → Run workflow. The summary shows the issue link and the run's cost.

Notes:
- PRs opened by `GITHUB_TOKEN` don't trigger `pull_request` workflows, so the writer validates drafts
  itself (one repair round, invalid drafts are dropped) and then dispatches `validate` on the branch.
- Pause the three Grok automations (grok.com → Settings → Automations) so they don't run in parallel.
- Daylight saving: the crons are fixed UTC, so in summer they run one hour later local time.

## 3c. Grok collects, Claude writes (active)

Two halves. No Claude token or GitHub secret is needed for the Claude half.

| Piece | When (UTC) | What |
|---|---|---|
| `daily` workflow (Grok) | 13:17 (GitHub often starts it hours late) | Grok searches X (≤ 12 searches) and commits raw data to `data/x/DATE.json`. Runs every `COLLECT_EVERY_DAYS` (default 2) days to save the Grok Plus allowance. Also stops when the last 7 days of collects cost ≥ `GROK_WEEKLY_BUDGET_USD` (default $4; each data file records its `cost_usd`). |
| Scheduled Claude Code session "daily" | ~15:xx | Claude reads `brain/`, the newest data, the ledger and recent queues, then opens "Engagement queue — DATE" and the "Drafts for DATE" PR. If collection is due and the data isn't there yet, it dispatches the `daily` workflow and waits. Instructions: `agents/claude/daily.md`. |
| Scheduled Claude Code session "weekly" | Sunday evening US Central | Claude analyses the ledger and opens "Weekly review — DATE" (+ a playbook PR when the evidence supports it). Instructions: `agents/claude/weekly.md`. |

The scheduled sessions run on your Claude plan (claude.ai/code → scheduled tasks), not in GitHub Actions.
Each is a fresh session with the repo attached; its prompt just says "clone/read the repo and follow `agents/claude/daily.md`".
Claude has no `gh` CLI there: it uses the GitHub tools, can only push to its own session branch, and can't merge.
That's fine: the publisher only cares that drafts arrive on `main` through a merged PR.

Setup (once): in the Claude Code session that built this, ask it to create the two scheduled tasks. Nothing to do on GitHub.

## 4. Dry run → first live post

1. **Actions → publish → Run workflow.** Open the run's Summary: it should say `DRY RUN` and either `nothing due` or `WOULD POST …`.
2. Make a test draft through a PR (or let Daily Writer make one), scheduled ~20 min ahead. Merge it. The `validate` check must be green.
3. Repo → **Settings → Secrets and variables → Actions → Variables → New variable**: `PUBLISH_ENABLED` = `true`.
4. After the scheduled time, the next run (at :07 / :37) posts it. Or run **publish** manually. The Summary shows the post URL, and `ledger/posts.jsonl` gets a line.

## Kill switch

Set `PUBLISH_ENABLED` to `false` (or **Actions → publish → ⋯ → Disable workflow**). Takes effect on the next run.

## How approval works (why no branch protection)

The publisher only posts a draft if the **last commit that touched the file is part of a PR merged into `main`**. So:
- Grok drafts → PR → you merge = approved.
- Anything pushed straight to `main` (by mistake or by Grok ignoring its rules) is **blocked** and shows as `BLOCKED` in the run summary.
- Don't add a "require pull request" rule to `main`, because the publisher needs to commit `ledger/` there.

## Troubleshooting

| Summary says | Fix |
|---|---|
| `X API HTTP 401` | Keys wrong, or the access token is read-only. Regenerate the access token after setting Read+Write. |
| `X API HTTP 402` / credits | Top up credits in the Developer Console. |
| `X API HTTP 403 … duplicate` | X refuses identical text. Change the draft. |
| `BLOCKED … not part of a merged PR` | The draft was edited directly on `main`. Re-submit it through a PR. |
| `skip … stale` | It was > 48 h late (e.g. publishing was disabled for days). Change `scheduled_at` in a PR. A draft merged after its slot but within 48 h just posts at the next free slot. |
| `defer … gap/cap` | Working as intended (≥ 90 min apart, ≤ 3/day). Tune in `publisher/config.json`. |
