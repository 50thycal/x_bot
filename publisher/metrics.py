"""Refresh engagement metrics for our own recent posts into ledger/posts.jsonl.

Only posts younger than metrics_max_age_days are refreshed, and only when a new
checkpoint (+1h, +6h, +24h, +72h, +168h after posting) has passed since the last
refresh. Reads of your own posts are the cheapest X API tier (~$0.001 each).
Makes zero API calls when nothing needs refreshing.
"""
from __future__ import annotations

import datetime as dt
import sys

from publisher import xbot

FIELDS = "public_metrics,non_public_metrics"


def needs_refresh(entry: dict, now: dt.datetime, cfg: dict) -> bool:
    if not entry.get("x_id") or not entry.get("posted_at"):
        return False
    posted = xbot.parse_time(entry["posted_at"])
    if now - posted > dt.timedelta(days=cfg["metrics_max_age_days"]):
        return False
    last = entry.get("metrics_refreshed_at")
    last_t = xbot.parse_time(last) if last else None
    passed = [posted + dt.timedelta(hours=h) for h in cfg["metrics_checkpoints_hours"]
              if posted + dt.timedelta(hours=h) <= now]
    if not passed:
        return False
    return last_t is None or last_t < passed[-1]


def to_metrics(tweet: dict) -> dict:
    pub = tweet.get("public_metrics", {}) or {}
    priv = tweet.get("non_public_metrics", {}) or {}
    return {
        "impressions": priv.get("impression_count", pub.get("impression_count")),
        "likes": pub.get("like_count"),
        "replies": pub.get("reply_count"),
        "reposts": pub.get("retweet_count"),
        "quotes": pub.get("quote_count"),
        "bookmarks": pub.get("bookmark_count"),
        "profile_clicks": priv.get("user_profile_clicks"),
        "url_clicks": priv.get("url_link_clicks"),
    }


def fetch(ids: list[str], creds: xbot.XCreds) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            resp = xbot.x_request("GET", "/tweets", creds, query={"ids": ",".join(batch), "tweet.fields": FIELDS})
        except xbot.XError:
            # non_public_metrics can be refused (e.g. app permissions); fall back to public only
            resp = xbot.x_request("GET", "/tweets", creds,
                                  query={"ids": ",".join(batch), "tweet.fields": "public_metrics"})
        for t in resp.get("data", []) or []:
            out[t["id"]] = t
    return out


def main() -> int:
    now = xbot.utcnow()
    cfg = xbot.load_config()
    ledger = xbot.load_ledger()
    due = [e for e in ledger if needs_refresh(e, now, cfg)]
    if not due:
        print("metrics: nothing to refresh")
        return 0
    creds = xbot.XCreds.from_env()
    if not creds:
        print("metrics: X_* secrets missing; skipping")
        return 0
    tweets = fetch([e["x_id"] for e in due], creds)
    updated = 0
    for e in due:
        t = tweets.get(e["x_id"])
        if not t:
            continue
        e["metrics"] = to_metrics(t)
        e["metrics_refreshed_at"] = xbot.iso(now)
        updated += 1
    xbot.write_ledger(ledger)
    print(f"metrics: refreshed {updated}/{len(due)} posts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
