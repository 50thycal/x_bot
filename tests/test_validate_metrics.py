import datetime as dt
import tempfile
import unittest
from pathlib import Path

from publisher import metrics, validate
from tests.test_xbot import CFG, make_draft

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)


class ValidateTest(unittest.TestCase):
    def test_schedule_rules(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            a = make_draft(tmp, "a", "2026-11-23T14:00:00Z")
            b = make_draft(tmp, "b", "2026-11-23T15:00:00Z")  # 60 min after a
            past = make_draft(tmp, "past", "2026-11-21T14:00:00Z")
            errs = " ".join(validate.validate_all(NOW, CFG, [a, b, past], []))
            self.assertIn("only 60 min", errs)
            self.assertIn("in the past", errs)

    def test_clean_schedule_and_daily_cap(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ds = [make_draft(tmp, f"d{i}", f"2026-11-23T{10 + 2 * i:02d}:00:00Z") for i in range(3)]
            self.assertEqual(validate.validate_all(NOW, CFG, ds, []), [])
            ds.append(make_draft(tmp, "d3", "2026-11-23T20:00:00Z"))
            self.assertIn("max 3", " ".join(validate.validate_all(NOW, CFG, ds, [])))

    def test_reused_id(self):
        with tempfile.TemporaryDirectory() as t:
            a = make_draft(Path(t), "a", "2026-11-23T14:00:00Z")
            errs = validate.validate_all(NOW, CFG, [a], [{"id": "a", "posted_at": "2026-11-20T10:00:00Z"}])
            self.assertTrue(any("already posted" in e for e in errs))


class MetricsTest(unittest.TestCase):
    def test_checkpoints(self):
        e = {"x_id": "1", "posted_at": "2026-11-22T10:30:00Z", "metrics_refreshed_at": None}
        self.assertTrue(metrics.needs_refresh(e, NOW, CFG))            # +1h passed
        e["metrics_refreshed_at"] = "2026-11-22T11:45:00Z"
        self.assertFalse(metrics.needs_refresh(e, NOW, CFG))           # next checkpoint is +6h
        young = {"x_id": "2", "posted_at": "2026-11-22T11:30:00Z"}
        self.assertFalse(metrics.needs_refresh(young, NOW, CFG))       # < 1h old
        old = {"x_id": "3", "posted_at": "2026-10-01T00:00:00Z"}
        self.assertFalse(metrics.needs_refresh(old, NOW, CFG))         # too old

    def test_mapping(self):
        m = metrics.to_metrics({"public_metrics": {"like_count": 4, "impression_count": 50},
                                "non_public_metrics": {"impression_count": 60, "user_profile_clicks": 2}})
        self.assertEqual((m["likes"], m["impressions"], m["profile_clicks"]), (4, 60, 2))
