import datetime as dt
import unittest
from unittest import mock

from agents import run, xai
from publisher import xbot

UTC = dt.timezone.utc


class ParseTest(unittest.TestCase):
    def test_parse_response_text_and_citations(self):
        data = {"output": [
            {"type": "custom_tool_call", "call_id": "xs_1"},
            {"type": "message", "content": [{"type": "output_text", "text": "hello",
                                             "annotations": [{"type": "url_citation", "url": "https://x.com/a/status/1"}]}]},
        ]}
        self.assertEqual(xai.parse_response(data), ("hello", ["https://x.com/a/status/1"]))

    def test_read_sse_completed(self):
        resp = {"type": "response.completed", "response": {"model": "m", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "hi"}]}], "usage": {"input_tokens": 3}}}
        lines = [b"event: response.output_text.delta\n", b'data: {"type":"response.output_text.delta","delta":"h"}\n', b"\n",
                 b"event: response.completed\n", ("data: " + __import__("json").dumps(resp) + "\n").encode(), b"\n"]
        data = xai.read_sse(lines)
        self.assertEqual(xai.parse_response(data)[0], "hi")
        self.assertEqual(data["usage"]["input_tokens"], 3)

    def test_read_sse_deltas_and_errors(self):
        data = xai.read_sse([b'data: {"type":"response.output_text.delta","delta":"a"}\n', b"\n",
                             b'data: {"type":"response.output_text.delta","delta":"b"}\n'])
        self.assertEqual(xai.parse_response(data)[0], "ab")
        with self.assertRaises(xai.XAIError):
            xai.read_sse([b'data: {"type":"response.failed","response":{"error":{"message":"no credits"}}}\n', b"\n"])
        with self.assertRaises(xai.XAIError):
            xai.read_sse([b": keepalive\n", b"\n"])

    def test_cost(self):
        r = xai.Result(text="", model="m", usage={"cost_in_usd_ticks": 2_500_000_000})
        self.assertAlmostEqual(r.cost_usd, 0.25)
        self.assertIn("cost $0.2500", r.usage_line())

    def test_extract_json_prefers_fence(self):
        self.assertEqual(run.extract_json('blah {"x":0}\n```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(run.extract_json('sure: {"a": 2} done'), {"a": 2})
        with self.assertRaises(ValueError):
            run.extract_json("no json here")

    def test_strip_outer_fence(self):
        self.assertEqual(run.strip_outer_fence("```markdown\n## hi\n```"), "## hi")
        self.assertEqual(run.strip_outer_fence("## hi\n```\ncode\n```"), "## hi\n```\ncode\n```")


class WriterTest(unittest.TestCase):
    def test_target_date(self):
        d, earliest = run.writer_target(dt.datetime(2026, 11, 22, 2, 3, tzinfo=UTC))
        self.assertEqual(d, dt.date(2026, 11, 22))
        self.assertEqual(earliest, dt.datetime(2026, 11, 22, 3, 33, tzinfo=UTC))
        d, _ = run.writer_target(dt.datetime(2026, 11, 22, 15, 0, tzinfo=UTC))
        self.assertEqual(d, dt.date(2026, 11, 23))

    def test_draft_text_roundtrip(self):
        stem, content = run.draft_text({
            "slug": "Phone Coding!", "pillar": "build", "product": "none",
            "scheduled_at": "2026-11-22T14:00:00Z", "why": "test\nline", "split": "val",
            "parts": ["one", "two"]}, dt.date(2026, 11, 22))
        self.assertEqual(stem, "2026-11-22-phone-coding")
        meta, body = xbot.parse_front_matter(content)
        self.assertEqual(meta["id"], stem)
        self.assertEqual(meta["type"], "thread")
        self.assertEqual(meta["split"], "val")
        self.assertEqual(meta["why"], "test line")
        self.assertEqual(xbot.split_parts(body), ["one", "two"])

    def test_check_drafts_flags_bad_and_cap(self):
        now = dt.datetime(2026, 11, 22, 2, 0, tzinfo=UTC)
        good = run.draft_text({"slug": "a", "pillar": "build", "product": "none",
                               "scheduled_at": "2026-11-22T14:00:00Z", "parts": ["fine post"]}, now.date())
        bad = run.draft_text({"slug": "b", "pillar": "nope", "product": "none",
                              "scheduled_at": "2026-11-22T14:30:00Z", "parts": ["see example.com TODO"]}, now.date())
        with mock.patch.object(xbot, "draft_paths", return_value=[]), \
                mock.patch.object(xbot, "load_ledger", return_value=[]):
            errs = run.check_drafts(dict([good, bad]), now)
        self.assertEqual(errs[good[0]], [])
        joined = " ".join(errs[bad[0]])
        for needle in ("pillar", "URL", "TODO", "min after"):
            self.assertIn(needle, joined)


if __name__ == "__main__":
    unittest.main()


class XLinksTest(unittest.TestCase):
    BODY = "\n".join([
        "I'll search first.## 🎯 Intent (reply personally, highest value)",
        "- [ ] https://x.com/SiobaYT/status/2124422648914444478 · @SiobaYT (185) · why: testers",
        "  > draft: Android and 14 days is a real window. Which fight breaks?",
        "",
        "## ➕ Follow suggestions",
        "- [ ] https://x.com/dvmartos · why: solo dev",
        "",
        "## ❤️ Like suggestions",
        "- [ ] https://x.com/dhh/status/2124474336996422046",
    ])

    def test_links(self):
        out = run.add_x_links(run.drop_preamble(self.BODY))
        self.assertTrue(out.startswith("## 🎯 Intent"))
        self.assertIn("  >\n  > [**Reply in X ↗**](https://x.com/intent/post?in_reply_to=2124422648914444478"
                      "&text=Android+and+14+days+is+a+real+window.+Which+fight+breaks%3F)", out)
        self.assertIn("· [Follow ↗](https://x.com/intent/follow?screen_name=dvmartos)", out)
        self.assertIn("· [Like ↗](https://x.com/intent/like?tweet_id=2124474336996422046)", out)
        # a status URL in the follow section is not mistaken for a profile
        self.assertNotIn("screen_name=SiobaYT", out)

    def test_no_preamble_untouched(self):
        self.assertEqual(run.drop_preamble("## A\nx"), "## A\nx")


class SeenBlockTest(unittest.TestCase):
    def test_only_links_deduped(self):
        issues = [{"title": "Engagement queue — 2026-11-22", "body":
                   "- [ ] https://x.com/a/status/1 · why\n  > draft: long text here\n"
                   "- [ ] https://x.com/bob · why\n- [ ] https://x.com/a/status/1"}]
        self.assertEqual(run.seen_block(issues),
                         "Engagement queue — 2026-11-22: https://x.com/a/status/1 https://x.com/bob")
        self.assertEqual(run.seen_block([]), "(none yet)")
