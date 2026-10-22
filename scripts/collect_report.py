#!/usr/bin/env python3
"""Collect per-person iOS/Android ticket ownership + PR counts into data/report.json."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bitbucket_client import BitbucketClient
from app.jira_client import JiraClient
from app.ownership import matches_name, normalize_name, resolve_owner


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def month_bounds(month: str) -> tuple[str, str]:
    """month=YYYY-MM → inclusive JQL resolved dates in Bangkok (+07)."""
    start = date.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start.isoformat(), end.isoformat()


def aggregate_tickets(
    jira: JiraClient,
    month: str,
    project: str,
    qa_names: set[str],
    exclude_names: set[str],
) -> tuple[dict[str, Counter], list[dict[str, Any]]]:
    start, end = month_bounds(month)
    projects = [p.strip() for p in project.split(",") if p.strip()]
    project_clause = f"project = {projects[0]}" if len(projects) == 1 else f"project in ({', '.join(projects)})"
    jql = (
        f'{project_clause} AND resolved >= "{start}" AND resolved < "{end}" '
        f"ORDER BY resolved ASC"
    )
    issues = jira.search_issues(
        jql,
        fields=["summary", "assignee", "status", "resolutiondate", "created"],
    )

    id_to_issue: dict[str, dict[str, Any]] = {}
    keys: list[str] = []
    for issue in issues:
        issue_id = str(issue.get("id") or "")
        key = issue.get("key") or ""
        if not issue_id or not key:
            continue
        id_to_issue[issue_id] = issue
        keys.append(key)

    changelogs_by_id: dict[str, list[dict[str, Any]]] = {}
    if keys:
        try:
            changelogs_by_id = jira.bulk_changelogs(keys, field_ids=["assignee", "status"])
        except RuntimeError:
            # Fallback per-issue if bulk API unavailable
            for key in keys:
                issue = next(i for i in issues if i.get("key") == key)
                issue_id = str(issue.get("id"))
                changelogs_by_id[issue_id] = jira.issue_changelog(key)

    # bulkfetch may key by issue id only
    if not changelogs_by_id and keys:
        for key in keys:
            issue = id_to_issue[
                next(iid for iid, iss in id_to_issue.items() if iss.get("key") == key)
            ]
            changelogs_by_id[str(issue["id"])] = jira.issue_changelog(key)

    per_person: dict[str, Counter] = defaultdict(Counter)
    details: list[dict[str, Any]] = []
    exclude_norm = {normalize_name(n) for n in exclude_names} | {
        normalize_name(n) for n in qa_names
    }

    for issue_id, issue in id_to_issue.items():
        fields = issue.get("fields") or {}
        summary = fields.get("summary") or ""
        assignee = ((fields.get("assignee") or {}).get("displayName"))
        logs = changelogs_by_id.get(issue_id) or []
        result = resolve_owner(summary, assignee, logs, qa_names)
        owner = result.owner
        if not owner or matches_name(owner, exclude_names):
            details.append(
                {
                    "key": issue.get("key"),
                    "board": (issue.get("key") or "").split("-", 1)[0],
                    "summary": summary,
                    "owner": owner,
                    "platform": result.platform,
                    "method": result.method,
                    "note": result.note or "excluded",
                    "counted": False,
                }
            )
            continue

        platform = result.platform
        if platform == "iOS":
            per_person[owner]["tickets_ios"] += 1
        elif platform == "Android":
            per_person[owner]["tickets_android"] += 1
        elif platform == "Both":
            per_person[owner]["tickets_both"] += 1
        else:
            per_person[owner]["tickets_unknown"] += 1

        details.append(
            {
                "key": issue.get("key"),
                "board": (issue.get("key") or "").split("-", 1)[0],
                "summary": summary,
                "owner": owner,
                "platform": platform,
                "method": result.method,
                "note": result.note,
                "counted": True,
            }
        )

    return per_person, details


def aggregate_prs(
    bb: BitbucketClient,
    month: str,
    repos: dict[str, str],
    exclude_names: set[str],
    board_members: set[str],
    pages_per_repo: int,
) -> tuple[dict[str, Counter], dict[str, str]]:
    start, end = month_bounds(month)
    raw, ticket_owners = bb.count_merged_authors(repos, start=start, end=end, pages_per_repo=pages_per_repo)
    exclude_norm = {normalize_name(n) for n in exclude_names}
    out: dict[str, Counter] = defaultdict(Counter)
    for name, counter in raw.items():
        if matches_name(name, exclude_names) or not matches_name(name, board_members):
            continue
        out[name]["prs_ios"] = counter.get("iOS", 0)
        out[name]["prs_android"] = counter.get("Android", 0)
        out[name]["prs_mobile"] = counter.get("Mobile", 0)
    return out, ticket_owners


def merge_rows(
    ticket_counts: dict[str, Counter],
    pr_counts: dict[str, Counter],
    ticket_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    boards_by_name: dict[str, set[str]] = defaultdict(set)
    for detail in ticket_details:
        if detail.get("counted") and detail.get("owner") and detail.get("board"):
            boards_by_name[detail["owner"]].add(detail["board"])
    names = sorted(set(ticket_counts) | set(pr_counts), key=str.casefold)
    rows = []
    for name in names:
        t = ticket_counts.get(name) or Counter()
        p = pr_counts.get(name) or Counter()
        rows.append(
            {
                "name": name,
                "boards": sorted(boards_by_name.get(name, set())),
                "tickets_ios": int(t.get("tickets_ios", 0)),
                "tickets_android": int(t.get("tickets_android", 0)),
                "tickets_unknown": int(t.get("tickets_unknown", 0)),
                "tickets_both": int(t.get("tickets_both", 0)),
                "prs_ios": int(p.get("prs_ios", 0)),
                "prs_android": int(p.get("prs_android", 0)),
                "prs_mobile": int(p.get("prs_mobile", 0)),
            }
        )
    rows.sort(
        key=lambda r: (
            -(r["tickets_ios"] + r["tickets_android"] + r["tickets_both"] + r["tickets_unknown"]),
            -(r["prs_ios"] + r["prs_android"] + r["prs_mobile"]),
            r["name"].casefold(),
        )
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect ownership report")
    parser.add_argument("--month", default=date.today().strftime("%Y-%m"), help="YYYY-MM")
    parser.add_argument("--project", default="SC,IMP,LS,EXP,VAL", help="Comma-separated Jira project keys")
    parser.add_argument("--skip-prs", action="store_true")
    parser.add_argument("--skip-tickets", action="store_true")
    parser.add_argument("--pr-pages", type=int, default=40)
    parser.add_argument(
        "--prs-from",
        type=Path,
        help="Reuse existing people_platforms JSON instead of re-fetching PRs",
    )
    args = parser.parse_args()

    qa_names = set(load_json(ROOT / "config" / "qa_names.json"))
    exclude_names = set(load_json(ROOT / "config" / "exclude_names.json")) | qa_names
    board_members = set(load_json(ROOT / "config" / "board_members.json"))
    repos = load_json(ROOT / "config" / "repos.json")["repos"]

    ticket_counts: dict[str, Counter] = defaultdict(Counter)
    ticket_details: list[dict[str, Any]] = []
    if not args.skip_tickets:
        print(f"Fetching Jira tickets for {args.project} month {args.month}…")
        jira = JiraClient()
        ticket_counts, ticket_details = aggregate_tickets(
            jira, args.month, args.project, qa_names, exclude_names
        )
        print(f"  tickets: {len(ticket_details)} issues")

    pr_counts: dict[str, Counter] = defaultdict(Counter)
    pr_ticket_owners: dict[str, str] = {}
    if not args.skip_prs:
        if args.prs_from and args.prs_from.exists():
            print(f"Loading PR counts from {args.prs_from}")
            payload = load_json(args.prs_from)
            for person in payload.get("people") or []:
                name = person.get("name") or ""
                if matches_name(name, exclude_names) or not matches_name(name, board_members):
                    continue
                pr_counts[name]["prs_ios"] = int(person.get("ios_prs") or 0)
                pr_counts[name]["prs_android"] = int(person.get("android_prs") or 0)
                pr_counts[name]["prs_mobile"] = int(person.get("mobile_prs") or 0)
        else:
            print("Fetching Bitbucket merged PRs across 9 repos…")
            bb = BitbucketClient()
            pr_counts, pr_ticket_owners = aggregate_prs(bb, args.month, repos, exclude_names, board_members, args.pr_pages)

    for detail in ticket_details:
        pr_owner = pr_ticket_owners.get((detail.get("key") or "").upper())
        if detail.get("counted") and pr_owner and not matches_name(pr_owner, exclude_names):
            detail["owner"] = pr_owner
            detail["method"] = "pull_request_author"
    if pr_ticket_owners:
        ticket_counts = defaultdict(Counter)
        for detail in ticket_details:
            if not detail.get("counted") or not detail.get("owner"):
                continue
            platform = detail.get("platform")
            if platform == "iOS": ticket_counts[detail["owner"]]["tickets_ios"] += 1
            elif platform == "Android": ticket_counts[detail["owner"]]["tickets_android"] += 1
            elif platform == "Both": ticket_counts[detail["owner"]]["tickets_both"] += 1
            else: ticket_counts[detail["owner"]]["tickets_unknown"] += 1

    rows = merge_rows(ticket_counts, pr_counts, ticket_details)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "month": args.month,
        "project": args.project,
        "rows": rows,
        "ticket_details": ticket_details,
        "notes": {
            "tickets": "Owner = last non-QA assignee before QA, or In Progress author / longest non-QA assignee",
            "prs": "Merged PR authors from 9 /reviewpr repos; platform from repo",
            "qa_excluded": sorted(qa_names),
        },
    }
    out = ROOT / "data" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote {out} ({len(rows)} people)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
