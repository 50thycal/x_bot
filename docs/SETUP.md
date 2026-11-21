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
| `skip … stale` | It was > 3 h late (e.g. publishing was disabled). Change `scheduled_at` in a PR. |
| `defer … gap/cap` | Working as intended (≥ 90 min apart, ≤ 3/day). Tune in `publisher/config.json`. |
