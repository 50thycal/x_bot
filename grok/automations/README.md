# Grok automations

Create each of these at **grok.com/automations** (or Grok app → Automations).
Paste the prompt file's contents (everything under "## Prompt") as the automation prompt.

| File | Schedule | Output |
|---|---|---|
| `01-daily-scout.md` | Daily 08:00 your time | GitHub issue "Engagement queue — DATE" |
| `02-daily-writer.md` | Daily 20:00 your time | PR adding 2–3 drafts to `queue/` |
| `03-weekly-review.md` | Sunday 18:00 | PR editing `brain/playbook.md` + issue "Weekly review — DATE" |

Replace `OWNER/x_bot` with this repo's full name in each prompt (`50thycal/x_bot`).

## First-run checklist
1. Fill every TODO in `brain/`.
2. Run Daily Scout manually once. Confirm an issue appears in this repo.
   - If Grok can search X but cannot create the issue from an automation, see `docs/PLAN.md` → Fallback B.
3. Run Daily Writer manually. Confirm a PR appears and touches only `queue/`.
4. Do NOT add a "require pull request" branch protection on `main`: the publisher commits the ledger there.
   Approval is enforced by the publisher instead: it only posts a draft whose last commit is part of a merged PR.
