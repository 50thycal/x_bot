import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import collect

NOW = dt.datetime(2026, 11, 23, 14, 0, tzinfo=dt.timezone.utc)


class CollectTest(unittest.TestCase):
    def test_section(self):
        md = "## Niche search queries (x)\n- a\n- b\n\n## Never engage\n- c\n"
        self.assertEqual(collect.section(md, "Niche search queries"), "- a\n- b")
        self.assertEqual(collect.section(md, "never engage"), "- c")

    def test_clean_dedups_validates_and_scores(self):
        raw = {"posts": [
            {"url": "https://x.com/a/status/1", "author": "@a", "author_followers": 100, "views": 2500,
             "posted_at": "2026-11-23T11:00:00Z", "text": "x" * 900},
            {"url": "https://x.com/a/status/1", "author": "a"},             # duplicate
            {"url": "https://x.com/b/status/2", "author": "b"},             # seen before
            {"url": "https://example.com/not-x", "author": "c"},            # not an X post
            {"url": "https://x.com/d/status/4", "author": "d", "views": "lots", "author_followers": None},
        ], "accounts": [{"handle": "@good_one"}, {"handle": "bad handle!"}], "trends": [{"topic": "t"}, {}]}
        out = collect.clean(raw, {"https://x.com/b/status/2"}, NOW)
        self.assertEqual([p["url"] for p in out["posts"]], ["https://x.com/a/status/1", "https://x.com/d/status/4"])
        a = out["posts"][0]
        self.assertEqual((a["author"], a["gold_ratio"], a["age_h"], len(a["text"])), ("a", 25.0, 3.0, 400))
        self.assertIsNone(out["posts"][1]["views"])
        self.assertIsNone(out["posts"][1]["gold_ratio"])
        self.assertEqual([x["handle"] for x in out["accounts"]], ["good_one"])
        self.assertEqual(len(out["trends"]), 1)

    def test_skips_when_weekly_budget_spent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "2026-11-19.json").write_text('{"cost_usd": 2.5}')
            (p / "2026-11-21.json").write_text('{"cost_usd": 2.0}')
            (p / "2026-11-01.json").write_text('{"cost_usd": 99}')   # older than 7 days: ignored
            with mock.patch.object(collect, "DATA_DIR", p), mock.patch.object(collect.xai, "respond") as r, \
                 mock.patch.dict("os.environ", {"COLLECT_EVERY_DAYS": "1", "GROK_WEEKLY_BUDGET_USD": "4"}):
                self.assertEqual(collect.week_spend(NOW), (4.5, 2))
                self.assertEqual(collect.collect(NOW, False), 0)
                r.assert_not_called()

    def test_skips_when_recent_data_exists(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "2026-11-22.json").write_text("{}")
            with mock.patch.object(collect, "DATA_DIR", p), mock.patch.object(collect.xai, "respond") as r, \
                 mock.patch.dict("os.environ", {"COLLECT_EVERY_DAYS": "2"}):
                self.assertEqual(collect.collect(NOW, dry_run=False), 0)
                r.assert_not_called()


class LinksCliTest(unittest.TestCase):
    def test_in_place(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "q.md"
            f.write_text("preamble## 🎯 Builders\n- [ ] https://x.com/a/status/9 · why\n  > draft: hi there\n")
            subprocess.run([sys.executable, "-m", "agents.links", str(f)], check=True,
                           cwd=Path(__file__).resolve().parents[1])
            out = f.read_text()
            self.assertTrue(out.startswith("## 🎯 Builders"))
            self.assertIn("intent/post?in_reply_to=9&text=hi+there", out)
