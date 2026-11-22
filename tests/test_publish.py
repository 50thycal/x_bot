import datetime as dt
import tempfile
import unittest
from pathlib import Path

from publisher import publish, xbot
from tests.test_xbot import CFG, make_draft

NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=dt.timezone.utc)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_due_future_stale_hold(self):
        due = make_draft(self.tmp, "due", "2026-11-22T14:45:00Z")
        future = make_draft(self.tmp, "future", "2026-11-22T18:00:00Z")
        stale = make_draft(self.tmp, "stale", "2026-11-22T09:00:00Z")
        held = make_draft(self.tmp, "held", "2026-11-22T14:50:00Z", hold="true")
        to_post, notes = publish.plan(NOW, CFG, [due, future, stale, held], [])
        self.assertEqual([d.id for d in to_post], ["due"])
        joined = " ".join(notes)
        self.assertIn("stale", joined)
        self.assertIn("hold", joined)

    def test_late_merge_rolls_forward_one_at_a_time(self):
        # Real config: drafts merged hours after their slot still post, oldest first, one per run.
        cfg = xbot.load_config()
        a = make_draft(self.tmp, "a", "2026-11-22T09:00:00Z")   # 6 h late
        b = make_draft(self.tmp, "b", "2026-11-22T11:30:00Z")
        to_post, notes = publish.plan(NOW, cfg, [b, a], [])
        self.assertEqual([d.id for d in to_post], ["a"])
        self.assertIn("defer b", " ".join(notes))
        old = make_draft(self.tmp, "old", "2026-11-19T09:00:00Z")  # > 48 h late
        self.assertEqual(publish.plan(NOW, cfg, [old], [])[0], [])

    def test_already_posted_and_gap_and_cap(self):
        d = make_draft(self.tmp, "d", "2026-11-22T14:50:00Z")
        self.assertEqual(publish.plan(NOW, CFG, [d], [{"id": "d", "posted_at": "2026-11-22T10:00:00Z"}])[0], [])
        recent = [{"id": "x", "posted_at": "2026-11-22T14:00:00Z"}]
        self.assertEqual(publish.plan(NOW, CFG, [d], recent)[0], [])  # 60 min < 90 min gap
        capped = [{"id": f"x{i}", "posted_at": f"2026-11-22T0{i}:00:00Z"} for i in range(3)]
        self.assertEqual(publish.plan(NOW, CFG, [d], capped)[0], [])  # 3/day cap

    def test_one_per_run(self):
        a = make_draft(self.tmp, "a", "2026-11-22T14:30:00Z")
        b = make_draft(self.tmp, "b", "2026-11-22T14:40:00Z")
        self.assertEqual([x.id for x in publish.plan(NOW, CFG, [b, a], [])[0]], ["a"])

    def test_invalid_skipped(self):
        bad = make_draft(self.tmp, "bad", "2026-11-22T14:30:00Z", body="link https://a.com")
        to_post, notes = publish.plan(NOW, CFG, [bad], [])
        self.assertEqual(to_post, [])
        self.assertIn("invalid", notes[0])


class PublishOneTest(unittest.TestCase):
    def test_thread_posts_as_self_replies_and_logs(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = make_draft(tmp, "th", "2026-11-22T14:30:00Z", body="one\n---8<---\ntwo", type="thread")
            calls = []

            def poster(text, reply_to):
                calls.append((text, reply_to))
                return str(100 + len(calls))

            ledger = tmp / "l.jsonl"
            e = publish.publish_one(d, poster, NOW, ledger)
            self.assertEqual(calls, [("one", None), ("two", "101")])
            self.assertEqual(e["x_ids"], ["101", "102"])
            self.assertEqual(e["status"], "posted")
            self.assertEqual(xbot.load_ledger(ledger)[0]["id"], "th")

    def test_partial_thread_is_logged(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = make_draft(tmp, "th", "2026-11-22T14:30:00Z", body="one\n---8<---\ntwo", type="thread")
            n = {"i": 0}

            def poster(text, reply_to):
                n["i"] += 1
                if n["i"] == 2:
                    raise RuntimeError("boom")
                return "101"

            e = publish.publish_one(d, poster, NOW, tmp / "l.jsonl")
            self.assertEqual(e["status"], "partial")
            self.assertEqual(e["x_ids"], ["101"])

    def test_first_part_failure_logs_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = make_draft(tmp, "a", "2026-11-22T14:30:00Z")

            def poster(text, reply_to):
                raise RuntimeError("403")

            with self.assertRaises(RuntimeError):
                publish.publish_one(d, poster, NOW, tmp / "l.jsonl")
            self.assertEqual(xbot.load_ledger(tmp / "l.jsonl"), [])
