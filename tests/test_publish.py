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


class MediaTest(unittest.TestCase):
    def test_video_uploaded_first_and_attached_to_part_one(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "clip.mp4").write_bytes(b"x" * 10)
            d = make_draft(tmp, "vid", "2026-11-22T14:30:00Z", body="one\n---8<---\ntwo", type="thread",
                           media="clip.mp4")
            d.meta["media"] = str(tmp / "clip.mp4")      # absolute path joins cleanly onto ROOT
            calls = []

            def poster(text, reply_to, media_ids=None):
                calls.append((text, reply_to, media_ids))
                return str(100 + len(calls))

            e = publish.publish_one(d, poster, NOW, tmp / "l.jsonl", uploader=lambda p: "m1")
            self.assertEqual(calls, [("one", None, ["m1"]), ("two", "101", None)])
            self.assertTrue(e["features"]["has_media"])

    def test_upload_failure_posts_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "clip.mp4").write_bytes(b"x")
            d = make_draft(tmp, "vid2", "2026-11-22T14:30:00Z", body="hi", media=str(tmp / "clip.mp4"))
            posted = []

            def boom(p):
                raise RuntimeError("nope")

            with self.assertRaises(RuntimeError):
                publish.publish_one(d, lambda *a, **k: posted.append(a) or "1", NOW, tmp / "l.jsonl", uploader=boom)
            self.assertEqual(posted, [])
            self.assertFalse((tmp / "l.jsonl").exists())

    def test_validate_missing_and_wrong_media(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = make_draft(tmp, "m3", "2026-11-22T14:30:00Z", body="hi", media="queue/media/does-not-exist.mp4")
            self.assertTrue(any("media file not found" in e for e in xbot.validate_draft(d, CFG)))
            (tmp / "a.mov").write_bytes(b"x")
            d2 = make_draft(tmp, "m4", "2026-11-22T14:30:00Z", body="hi", media=str(tmp / "a.mov"))
            self.assertTrue(any("must be .mp4" in e for e in xbot.validate_draft(d2, CFG)))

    def test_upload_video_flow(self):
        calls = []

        def fake_request(method, path, creds, query=None, body=None):
            calls.append((method, path))
            if path.endswith("/initialize"):
                return {"data": {"id": "42"}}
            if path.endswith("/finalize"):
                return {"data": {"id": "42", "processing_info": {"state": "pending", "check_after_secs": 1}}}
            return {"data": {"processing_info": {"state": "succeeded"}}}

        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "c.mp4"
            f.write_bytes(b"x" * (xbot.CHUNK_BYTES + 5))        # two chunks
            parts = []
            orig_req, orig_mp = xbot.x_request, xbot._x_multipart
            xbot.x_request = fake_request
            xbot._x_multipart = lambda path, creds, fields, name, data: parts.append((path, fields["segment_index"], len(data)))
            try:
                mid = xbot.upload_video(f, xbot.XCreds("a", "b", "c", "d"), sleep=lambda s: None)
            finally:
                xbot.x_request, xbot._x_multipart = orig_req, orig_mp
        self.assertEqual(mid, "42")
        self.assertEqual(parts, [("/media/upload/42/append", 0, xbot.CHUNK_BYTES), ("/media/upload/42/append", 1, 5)])
        self.assertEqual([c[1] for c in calls], ["/media/upload/initialize", "/media/upload/42/finalize", "/media/upload"])
