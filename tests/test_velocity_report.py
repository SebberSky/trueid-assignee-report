import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.prepare_velocity_report import build_report, load_reports


class VelocityReportTests(unittest.TestCase):
    def test_platforms_boards_excludes_and_missing_months(self):
        def ticket(owner, board, platform, points, counted=True):
            return dict(owner=owner, board=board, platform=platform, points=points, counted=counted)

        reports = {
            1: {"ticket_details": [ticket("Dev", "SC", "iOS", 3), ticket("Dev", "IMP", "iOS", 8),
                                   ticket("Dev", "SC", "Android", 5), ticket("Excluded (Ext)", "SC", "iOS", 99),
                                   ticket("QA", "SC", "iOS", 99, False)]},
            2: {"ticket_details": [ticket("Dev", "SC", "iOS", 0)]},
            10: {"ticket_details": [ticket("Dev", "SC", "iOS", 2)]},
        }
        result = build_report(reports, date(2026, 10, 28), {"Excluded"})
        self.assertEqual([sheet["name"] for sheet in result["sheets"]], ["iOS", "Android"])
        ios = result["sheets"][0]["rows"]
        self.assertEqual(ios[0], ["SC", "Dev", 3, 0, None, None, None, None, None, None, None, 2, None, None])
        self.assertEqual(ios[1][:3], ["IMP", "Dev", 8])
        self.assertEqual(result["sheets"][1]["rows"][0][:3], ["SC", "Dev", 5])

    def test_missing_points_are_not_fabricated_as_zero(self):
        reports = {1: {"ticket_details": [
            {"owner": "Dev", "board": "SC", "platform": "iOS", "counted": True},
            {"owner": "Dev", "board": "SC", "platform": "iOS", "counted": True, "points": 5},
        ]}}
        row = build_report(reports, date(2026, 10, 28), set())["sheets"][0]["rows"][0]
        self.assertIsNone(row[2])

    def test_latest_month_can_be_report_json_and_future_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text(json.dumps({"month": "2026-10", "generated_at": "2026-10-27"}))
            (root / "report-2026-10.json").write_text(json.dumps({"month": "2026-10", "generated_at": "2026-10-01"}))
            (root / "report-2026-12.json").write_text(json.dumps({"month": "2026-12"}))
            result = load_reports(root, date(2026, 10, 28))
            self.assertEqual(list(result), [10])
            self.assertEqual(result[10]["generated_at"], "2026-10-27")


if __name__ == "__main__":
    unittest.main()
