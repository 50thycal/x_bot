import datetime as dt
import tempfile
import unittest
from pathlib import Path

from publisher import xbot

CFG = {
    "max_posts_per_day": 3, "min_gap_minutes": 90, "max_posts_per_run": 1,
    "max_lateness_minutes": 180, "max_thread_parts": 5,
    "pillars": ["build", "devlog"], "products": ["none", "board-game"],
    "metrics_checkpoints_hours": [1, 6, 24, 72, 168], "metrics_max_age_days": 28,
}


def make_draft(tmp: Path, id_: str, when: str, body: str = "Cut 40% of the rules. Playtests got 2x faster.",
               **extra) -> xbot.Draft:
    meta = {"id": id_, "type": "original", "pillar": "build", "product": "none", "scheduled_at": when}
    meta.update(extra)
    text = "---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n" + body + "\n"
    p = tmp / f"{id_}.md"
    p.write_text(text)
    return xbot.load_draft(p)


class OAuthTest(unittest.TestCase):
    def test_signature_matches_twitter_docs_vector(self):
        # https://developer.x.com/en/docs/authentication/oauth-1-0a/creating-a-signature
        params = {
            "status": "Hello Ladies + Gentlemen, a signed OAuth request!",
            "include_entities": "true",
            "oauth_consumer_key": "xvz1evFS4wEEPTGEFPHBog",
            "oauth_nonce": "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": "1318622958",
            "oauth_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
            "oauth_version": "1.0",
        }
        sig = xbot.oauth1_signature(
            "POST", "https://api.twitter.com/1.1/statuses/update.json", params,
            "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE")
        self.assertEqual(sig, "hCtSmYh+iHYCEqBWrE7C7hYmtUk=")

    def test_header_shape(self):
        c = xbot.XCreds("k", "s", "t", "ts")
        h = xbot.oauth1_header("POST", "https://api.x.com/2/tweets", {}, c, nonce="n", timestamp="1")
        self.assertTrue(h.startswith("OAuth "))
        for k in ("oauth_consumer_key", "oauth_signature", "oauth_token", "oauth_nonce"):
            self.assertIn(k, h)


class DraftTest(unittest.TestCase):
    def test_front_matter_and_threads(self):
        meta, body = xbot.parse_front_matter(
            "---\nid: a\ntype: thread   # original | thread\nneeds_media: false\n"
            "brain_refs: [brain/a.md, brain/b.md]\n---\none\n---8<---\ntwo\n")
        self.assertEqual(meta["type"], "thread")
        self.assertIs(meta["needs_media"], False)
        self.assertEqual(meta["brain_refs"], ["brain/a.md", "brain/b.md"])
        self.assertEqual(xbot.split_parts(body), ["one", "two"])

    def test_missing_front_matter(self):
        with self.assertRaises(ValueError):
            xbot.parse_front_matter("no header")

    def test_weighted_length_and_urls(self):
        self.assertEqual(xbot.weighted_length("abc"), 3)
        self.assertEqual(xbot.weighted_length("🎲"), 2)
        self.assertTrue(xbot.has_url("see https://x.com"))
        self.assertTrue(xbot.has_url("go to mygame.com now"))
        self.assertFalse(xbot.has_url("v1.2 shipped. 3.5x faster."))

    def test_validate_draft(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ok = make_draft(tmp, "ok", "2026-11-22T14:00:00Z")
            self.assertEqual(xbot.validate_draft(ok, CFG), [])
            bad = make_draft(tmp, "bad", "2026-11-22T14:00:00Z", body="x" * 281 + " https://a.com TODO",
                             pillar="nope")
            errs = " ".join(xbot.validate_draft(bad, CFG))
            for needle in ("pillar", "(> 280)", "URL", "TODO"):
                self.assertIn(needle, errs)

    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "l.jsonl"
            xbot.append_ledger({"id": "a"}, p)
            xbot.append_ledger({"id": "b"}, p)
            self.assertEqual([e["id"] for e in xbot.load_ledger(p)], ["a", "b"])
