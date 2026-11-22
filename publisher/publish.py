"""Post approved, due drafts from queue/ to X.

Approved = the last commit touching the draft belongs to a PR merged into main.
Due      = scheduled_at <= now and not older than max_lateness_minutes (48 h by default:
           a draft approved after its slot posts at the next free slot; the caps
           below, not the lateness limit, are what prevent catch-up bursts).
Caps     = max_posts_per_day (UTC day), min_gap_minutes since the last post,
           max_posts_per_run.

Dry run unless PUBLISH_ENABLED=true. Each successful post is appended to
ledger/posts.jsonl immediately, so a crash never causes a double post.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
from typing import Callable

from publisher import xbot

Poster = Callable[[str, "str | None"], str]          # (text, reply_to_id) -> new post id
Approver = Callable[[xbot.Draft], "tuple[bool, str]"]  # draft -> (approved, reason)


def features_for(d: xbot.Draft, posted_at: dt.datetime) -> dict:
    first = d.parts[0] if d.parts else ""
    first_line = first.splitlines()[0] if first else ""
    return {
        "hook_words": len(first_line.split()),
        "chars": xbot.weighted_length(first),
        "parts": len(d.parts),
        "hour_utc": posted_at.hour,
        "weekday": posted_at.strftime("%a"),
        "has_media": False,
        "needs_media": bool(d.meta.get("needs_media", False)),
    }


def plan(now: dt.datetime, cfg: dict, drafts: list[xbot.Draft], ledger: list[dict]) -> tuple[list, list]:
    """Return (to_post, notes). Pure function: no I/O."""
    notes: list[str] = []
    posted_ids = {e["id"] for e in ledger}
    times = sorted(xbot.parse_time(e["posted_at"]) for e in ledger if e.get("posted_at"))
    today = now.date()
    posted_today = sum(1 for t in times if t.date() == today)
    last_post = times[-1] if times else None
    lateness = dt.timedelta(minutes=cfg["max_lateness_minutes"])
    gap = dt.timedelta(minutes=cfg["min_gap_minutes"])

    to_post = []
    candidates = []
    for d in drafts:
        if d.id in posted_ids:
            notes.append(f"skip {d.path.name}: already in ledger (will be moved to posted/)")
            continue
        errs = xbot.validate_draft(d, cfg)
        if errs:
            notes.append(f"skip {d.path.name}: invalid -> {'; '.join(errs)}")
            continue
        if d.hold:
            notes.append(f"skip {d.path.name}: hold: true")
            continue
        if d.scheduled_at > now:
            continue
        if now - d.scheduled_at > lateness:
            notes.append(f"skip {d.path.name}: stale (scheduled {xbot.iso(d.scheduled_at)}, "
                         f"> {cfg['max_lateness_minutes']} min late) - reschedule it")
            continue
        candidates.append(d)

    for d in sorted(candidates, key=lambda x: x.scheduled_at):
        if len(to_post) >= cfg["max_posts_per_run"]:
            notes.append(f"defer {d.path.name}: max_posts_per_run reached")
            continue
        if posted_today + len(to_post) >= cfg["max_posts_per_day"]:
            notes.append(f"defer {d.path.name}: daily cap {cfg['max_posts_per_day']} reached")
            continue
        if last_post and now - last_post < gap:
            notes.append(f"defer {d.path.name}: last post {xbot.iso(last_post)} is < {cfg['min_gap_minutes']} min ago")
            continue
        to_post.append(d)
    return to_post, notes


def publish_one(d: xbot.Draft, poster: Poster, now: dt.datetime, ledger_path=xbot.LEDGER_PATH) -> dict:
    ids: list[str] = []
    error = None
    for part in d.parts:
        try:
            ids.append(poster(part, ids[-1] if ids else None))
        except Exception as e:  # record partial threads so part 1 is never re-posted
            error = str(e)
            break
    if not ids:
        raise RuntimeError(f"{d.path.name}: first part failed: {error}")
    entry = {
        "id": d.id,
        "x_id": ids[0],
        "x_ids": ids,
        "url": f"https://x.com/i/status/{ids[0]}",
        "posted_at": xbot.iso(now),
        "scheduled_at": xbot.iso(d.scheduled_at),
        "type": d.meta.get("type"),
        "pillar": d.meta.get("pillar"),
        "product": d.meta.get("product"),
        "split": d.meta.get("split", "train"),
        "status": "partial" if error else "posted",
        "error": error,
        "text": d.body,
        "why": d.meta.get("why"),
        "features": features_for(d, now),
        "metrics": {},
        "metrics_refreshed_at": None,
    }
    xbot.append_ledger(entry, ledger_path)
    return entry


def archive(d: xbot.Draft) -> None:
    xbot.POSTED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d.path), str(xbot.POSTED_DIR / d.path.name))


def github_approver() -> Approver:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    base = os.environ.get("APPROVAL_BASE_BRANCH", "main")

    def approve(d: xbot.Draft):
        if os.environ.get("REQUIRE_PR_APPROVAL", "true").lower() == "false":
            return True, "approval check disabled"
        if not (repo and token):
            return False, "GITHUB_REPOSITORY/GITHUB_TOKEN not set; cannot verify PR approval"
        sha = xbot.last_commit_for(d.path)
        if not sha:
            return False, "file not committed"
        pr = xbot.merged_pr_for_commit(sha, repo, token, base)
        if pr is None:
            return False, f"last commit {sha[:7]} is not part of a merged PR into {base}"
        return True, f"approved via PR #{pr}"
    return approve


def x_poster(creds: xbot.XCreds) -> Poster:
    def post(text: str, reply_to: str | None) -> str:
        body: dict = {"text": text}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        resp = xbot.x_request("POST", "/tweets", creds, body=body)
        return resp["data"]["id"]
    return post


def summary(lines: list[str]) -> None:
    text = "\n".join(lines)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    now = xbot.utcnow()
    cfg = xbot.load_config()
    enabled = os.environ.get("PUBLISH_ENABLED", "").lower() == "true"
    ledger = xbot.load_ledger()
    drafts = []
    out = [f"## publish run {xbot.iso(now)} ({'LIVE' if enabled else 'DRY RUN'})", ""]
    for p in xbot.draft_paths():
        try:
            drafts.append(xbot.load_draft(p))
        except ValueError as e:
            out.append(f"- skip {p.name}: {e}")

    # housekeeping: anything already posted gets archived
    posted_ids = {e["id"] for e in ledger}
    for d in drafts:
        if d.id in posted_ids and enabled:
            archive(d)

    to_post, notes = plan(now, cfg, drafts, ledger)
    out += [f"- {n}" for n in notes]

    if not to_post:
        out.append("- nothing due")
        summary(out)
        return 0

    approver = github_approver()
    creds = xbot.XCreds.from_env()
    if enabled and not creds:
        out.append("- ERROR: PUBLISH_ENABLED=true but X_* secrets are missing")
        summary(out)
        return 1

    rc = 0
    for d in to_post:
        ok, reason = approver(d)
        if not ok:
            out.append(f"- BLOCKED {d.path.name}: {reason}")
            continue
        if not enabled:
            out.append(f"- WOULD POST {d.path.name} ({reason}, {len(d.parts)} part(s)):")
            out += [f"  > {line}" for line in d.body.splitlines()]
            continue
        try:
            entry = publish_one(d, x_poster(creds), now)
            archive(d)
            out.append(f"- POSTED {d.path.name} -> {entry['url']} [{entry['status']}] ({reason})")
            if entry["error"]:
                out.append(f"  thread stopped early: {entry['error']}")
                rc = 1
        except Exception as e:
            out.append(f"- FAILED {d.path.name}: {e}")
            rc = 1
    summary(out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
