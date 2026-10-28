#!/usr/bin/env python3
"""Prepare annual Jira-point data for the two-tab Google Sheets velocity report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.jira_client import JiraClient
from app.ownership import matches_name

BOARDS = ("SC", "IMP", "LS", "EXP", "VAL")
POINT_FIELDS = (
    "customfield_10124", "customfield_11210", "customfield_12714",
    "customfield_13828", "story_points", "customfield_10016",
)


def load_reports(directory: Path, today: date) -> dict[int, dict]:
    reports = {}
    # The month index points the latest month at report.json, not necessarily a dated file.
    for path in sorted(directory.glob(f"report-{today.year}-*.json")) + [directory / "report.json"]:
        if not path.exists():
            continue
        report = json.loads(path.read_text())
        month = date.fromisoformat(report["month"] + "-01")
        if month.year == today.year and month.month <= today.month:
            previous = reports.get(month.month)
            if previous is None or report.get("generated_at", "") >= previous.get("generated_at", ""):
                reports[month.month] = report
    return reports


def build_report(reports: dict[int, dict], today: date, excluded: set[str]) -> dict:
    sheets = []
    for platform in ("iOS", "Android"):
        monthly = defaultdict(dict)
        missing = set()
        for month, report in reports.items():
            for ticket in report.get("ticket_details", []):
                owner = ticket.get("owner")
                board = ticket.get("board")
                if (not ticket.get("counted") or not owner or board not in BOARDS
                        or ticket.get("platform") != platform or matches_name(owner, excluded)):
                    continue
                key = (board, owner)
                if ticket.get("points") is None:
                    missing.add((key, month))
                else:
                    monthly[key][month] = monthly[key].get(month, 0) + float(ticket["points"])
                monthly[key]  # Retain a name even when its points are unavailable.
        rows = []
        for board, person in sorted(monthly, key=lambda key: (BOARDS.index(key[0]), key[1].casefold())):
            values = [
                None if month > today.month or ((board, person), month) in missing
                else monthly[(board, person)].get(month)
                for month in range(1, 13)
            ]
            rows.append([board, person, *values])
        sheets.append({"name": platform, "rows": rows})
    return {
        "year": today.year,
        "as_of": today.isoformat(),
        "generated_at": datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(),
        "sources": {str(month): report.get("generated_at") for month, report in reports.items()},
        "sheets": sheets,
    }


def refresh_points(reports: dict[int, dict]) -> None:
    keys = sorted({ticket["key"] for report in reports.values()
                   for ticket in report.get("ticket_details", []) if ticket.get("key")})
    batches = [keys[index:index + 100] for index in range(0, len(keys), 100)]

    def fetch(batch):
        return JiraClient().search_issues("key in (" + ",".join(batch) + ")", fields=list(POINT_FIELDS))

    by_key = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, issues in enumerate(pool.map(fetch, batches), 1):
            for issue in issues:
                fields = issue.get("fields") or {}
                raw = next((fields[field] for field in POINT_FIELDS if fields.get(field) is not None), 0)
                by_key[issue["key"]] = float(raw)
            print(f"Jira points: {index}/{len(batches)} batches", flush=True)
    unavailable = set()
    for report in reports.values():
        for ticket in report.get("ticket_details", []):
            key = ticket.get("key")
            if key in by_key:
                ticket["points"] = by_key[key]
            elif ticket.get("points") is None:
                unavailable.add(key)
    print(f"Fetched {len(by_key)} Jira issues; {len(unavailable)} unavailable (left blank)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "dist" / "data")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(ZoneInfo("Asia/Bangkok")).date())
    parser.add_argument("--refresh-points", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = load_reports(args.reports, args.as_of)
    if not reports:
        raise SystemExit(f"No reports for {args.as_of.year}")
    if args.refresh_points:
        refresh_points(reports)
    excluded = set(json.loads((ROOT / "config" / "exclude_names.json").read_text()))
    excluded.update(json.loads((ROOT / "config" / "qa_names.json").read_text()))
    result = build_report(reports, args.as_of, excluded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Prepared {args.output}: " + ", ".join(f"{s['name']} {len(s['rows'])} rows" for s in result["sheets"]))


if __name__ == "__main__":
    main()
