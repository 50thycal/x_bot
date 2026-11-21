"""Validate every draft in queue/ (runs on pull requests).

Checks each draft's structure (see xbot.validate_draft) plus schedule-wide rules:
ids unique, not already posted, not scheduled in the past, >= min_gap_minutes
between any two posts (queued or already posted), <= max_posts_per_day per UTC day.
"""
from __future__ import annotations

import collections
import datetime as dt
import sys

from publisher import xbot


def validate_all(now: dt.datetime, cfg: dict, drafts: list[xbot.Draft], ledger: list[dict]) -> list[str]:
    errs: list[str] = []
    posted_ids = {e["id"] for e in ledger}
    seen: dict[str, str] = {}
    slots: list[tuple[dt.datetime, str]] = [
        (xbot.parse_time(e["posted_at"]), f"posted:{e['id']}") for e in ledger if e.get("posted_at")
    ]
    for d in drafts:
        name = d.path.name
        for e in xbot.validate_draft(d, cfg):
            errs.append(f"{name}: {e}")
        if d.id in seen:
            errs.append(f"{name}: duplicate id also used by {seen[d.id]}")
        seen[d.id] = name
        if d.id in posted_ids:
            errs.append(f"{name}: id already posted (see ledger) - pick a new id")
        try:
            t = d.scheduled_at
        except (KeyError, ValueError):
            continue
        if t < now - dt.timedelta(minutes=cfg["max_lateness_minutes"]) and d.id not in posted_ids:
            errs.append(f"{name}: scheduled_at {xbot.iso(t)} is in the past and would be skipped as stale")
        if not d.hold:
            slots.append((t, name))

    slots.sort()
    gap = dt.timedelta(minutes=cfg["min_gap_minutes"])
    for (t1, a), (t2, b) in zip(slots, slots[1:]):
        if t2 - t1 < gap and not (a.startswith("posted:") and b.startswith("posted:")):
            errs.append(f"{b}: only {int((t2 - t1).total_seconds() // 60)} min after {a} "
                        f"(min {cfg['min_gap_minutes']})")
    per_day = collections.Counter(t.date() for t, _ in slots)
    for day, n in sorted(per_day.items()):
        if n > cfg["max_posts_per_day"]:
            errs.append(f"{day}: {n} posts scheduled (max {cfg['max_posts_per_day']})")
    return errs


def main() -> int:
    cfg = xbot.load_config()
    drafts, errs = [], []
    for p in xbot.draft_paths():
        try:
            drafts.append(xbot.load_draft(p))
        except ValueError as e:
            errs.append(f"{p.name}: {e}")
    errs += validate_all(xbot.utcnow(), cfg, drafts, xbot.load_ledger())
    if errs:
        print("Draft validation FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"Draft validation OK ({len(drafts)} draft(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
