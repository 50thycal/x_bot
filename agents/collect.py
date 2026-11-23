"""Grok as a data source only: search X and save raw results to data/x/DATE.json.

    python -m agents.collect [--dry-run]

Claude (see agents/claude/) reads that file and does all the judging and writing.
Grok gets only the search queries, watched accounts and recently seen links, so each
run is small. Writes the file only; the workflow commits it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

from agents import xai
from agents.run import extract_json, int_env, read, summary
from publisher import xbot
from publisher.xbot import ROOT

DATA_DIR = ROOT / "data" / "x"
PROMPT = ROOT / "agents" / "prompts" / "collector.md"
STATUS = re.compile(r"^https://(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/\d+$")


def section(md: str, heading: str) -> str:
    """Return the bullet lines under a '## heading' in a markdown file."""
    out, on = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            on = heading.lower() in line.lower()
            continue
        if on and line.strip().startswith("-"):
            out.append(line.strip())
    return "\n".join(out)


def recent_links(days: int = 7) -> set[str]:
    seen: set[str] = set()
    for p in sorted(DATA_DIR.glob("*.json"))[-days:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seen.update(x.get("url", "") for x in d.get("posts", []))
    return seen


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def clean(data: dict, seen: set[str], now: dt.datetime) -> dict:
    """Drop malformed or repeated items, normalise numbers, add the gold ratio (views / followers)."""
    posts, urls = [], set()
    for p in data.get("posts") or []:
        url = str(p.get("url", "")).strip()
        if not STATUS.match(url) or url in seen or url in urls:
            continue
        urls.add(url)
        item = {
            "url": url,
            "author": str(p.get("author", "")).lstrip("@"),
            "author_followers": _num(p.get("author_followers")),
            "posted_at": p.get("posted_at"),
            "views": _num(p.get("views")),
            "likes": _num(p.get("likes")),
            "replies": _num(p.get("replies")),
            "reposts": _num(p.get("reposts")),
            "text": str(p.get("text", ""))[:400],
            "matched": str(p.get("matched", ""))[:80],
        }
        f, v = item["author_followers"], item["views"]
        item["gold_ratio"] = round(v / f, 1) if f and v is not None else None
        try:
            item["age_h"] = round((now - xbot.parse_time(item["posted_at"])).total_seconds() / 3600, 1)
        except (TypeError, ValueError):
            item["age_h"] = None
        posts.append(item)
    mentions = [m for m in data.get("mentions") or [] if STATUS.match(str(m.get("url", "")))]
    accounts = [a for a in data.get("accounts") or [] if re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", str(a.get("handle", "")))]
    for a in accounts:
        a["handle"] = str(a["handle"]).lstrip("@")
    trends = [t for t in data.get("trends") or [] if t.get("topic")][:5]
    return {"posts": posts, "mentions": mentions[:20], "accounts": accounts[:10], "trends": trends}


def week_spend(now: dt.datetime) -> tuple[float, int]:
    """Grok cost (USD) and number of collects in the last 7 days, from the files themselves."""
    total, n = 0.0, 0
    for p in DATA_DIR.glob("*.json") if DATA_DIR.exists() else []:
        try:
            if (now.date() - dt.date.fromisoformat(p.stem)).days >= 7:
                continue
            c = json.loads(p.read_text(encoding="utf-8")).get("cost_usd")
        except (OSError, ValueError):
            continue
        n += 1
        total += c if isinstance(c, (int, float)) else float(os.environ.get("COLLECT_COST_GUESS_USD", "1.0"))
    return total, n


def collect(now: dt.datetime, dry_run: bool) -> int:
    date = now.date().isoformat()
    out = DATA_DIR / f"{date}.json"
    if out.exists() and not dry_run:
        summary([f"## Collect\nskip: {out.relative_to(ROOT)} already exists"])
        return 0
    every = int_env("COLLECT_EVERY_DAYS", 2)  # Grok allowance: collect every N days, Claude reuses the latest file
    latest = sorted(DATA_DIR.glob("*.json"))[-1:] if DATA_DIR.exists() else []
    if latest and not dry_run and every > 1:
        try:
            age = (now.date() - dt.date.fromisoformat(latest[0].stem)).days
        except ValueError:
            age = every
        if age < every:
            summary([f"## Collect\nskip: {latest[0].name} is {age} day(s) old (COLLECT_EVERY_DAYS={every})"])
            return 0
    cap = float(os.environ.get("GROK_WEEKLY_BUDGET_USD", "").strip() or 4.0)  # keep well inside the Grok Plus weekly allowance
    spent, runs = week_spend(now)
    if not dry_run and spent >= cap:
        summary([f"## Collect\nskip: ${spent:.2f} spent on {runs} collect(s) in the last 7 days, cap ${cap:.2f} (GROK_WEEKLY_BUDGET_USD)"])
        return 0
    targets = read("brain/targets.md")
    seen = recent_links()
    user = "\n".join([
        f"Today is {date} (UTC). Window: posts from the last 48 hours, mentions from the last 72 hours.",
        "", "SEARCH QUERIES:", section(targets, "Niche search queries"), section(targets, "Builder phrases"),
        "", "WATCHED ACCOUNTS:", section(targets, "Accounts / lists to watch"),
        "", "NEVER INCLUDE:", section(targets, "Never engage"),
        "", "ALREADY COLLECTED (skip these):", " ".join(sorted(seen)[-150:]) or "(none)",
    ])
    res = xai.respond(user, instructions=PROMPT.read_text(encoding="utf-8"),
                      model=os.environ.get("XAI_SCOUT_MODEL", "").strip() or None,
                      tools=[xai.x_search_tool(from_date=(now - dt.timedelta(days=3)).date().isoformat())],
                      max_turns=int_env("XAI_SCOUT_MAX_TURNS", 3))
    try:
        data = clean(extract_json(res.text), seen, now)
    except (ValueError, json.JSONDecodeError) as e:
        summary(["## Collect\nFAILED: could not parse Grok's answer", str(e), res.usage_line(), "", res.text[:2000]])
        return 1
    data = {"date": date, "collected_at": xbot.iso(now), "usage": res.usage_line(),
            "cost_usd": res.cost_usd, **data}
    counts = ", ".join(f"{k} {len(data[k])}" for k in ("posts", "mentions", "accounts", "trends"))
    if dry_run:
        summary([f"## Collect (dry run)\n{counts}", res.usage_line(), "", "```json", json.dumps(data, indent=1)[:6000], "```"])
        return 0
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary([f"## Collect\nWROTE {out.relative_to(ROOT)}: {counts}", res.usage_line()])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        return collect(xbot.utcnow(), args.dry_run)
    except xai.XAIError as e:
        summary([f"## Collect\nFAILED: {e}"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
