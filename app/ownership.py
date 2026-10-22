"""Resolve who actually held a Jira ticket (exclude QA closing assignees)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any  # noqa: F401 — used by _parse_ts / resolve_owner


PLATFORM_RE = re.compile(r"\[(iOS|Android)(?:\s|[^\]]*)?\]", re.IGNORECASE)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(name.strip().split()).casefold()


def matches_name(name: str | None, known_names: set[str]) -> bool:
    """Match a known full name even when Jira appends extra text."""
    normalized = normalize_name(name)
    return bool(normalized) and any(
        normalized_known and normalized_known in normalized
        for normalized_known in (normalize_name(value) for value in known_names)
    )


def detect_ticket_platform(summary: str) -> str:
    matches = PLATFORM_RE.findall(summary or "")
    platforms = {m.lower() for m in matches}
    if "ios" in platforms and "android" not in platforms:
        return "iOS"
    if "android" in platforms and "ios" not in platforms:
        return "Android"
    if "ios" in platforms and "android" in platforms:
        return "Both"
    return "Unknown"


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Jira sometimes returns epoch millis
        seconds = value / 1000.0 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass
class OwnershipResult:
    owner: str | None
    method: str
    note: str
    platform: str


def resolve_owner(
    summary: str,
    current_assignee: str | None,
    changelogs: list[dict[str, Any]],
    qa_names: set[str],
) -> OwnershipResult:
    """Pick ticket owner from assignee history / In Progress transition."""
    qa = {normalize_name(n) for n in qa_names}
    platform = detect_ticket_platform(summary)

    assignee_events: list[tuple[datetime, str | None, str | None]] = []
    in_progress_authors: list[tuple[datetime, str]] = []

    for entry in changelogs:
        created = _parse_ts(entry.get("created"))
        if created is None:
            continue
        author = ((entry.get("author") or {}).get("displayName")
                  or (entry.get("author") or {}).get("display_name")
                  or "")
        for item in entry.get("items") or []:
            field = (item.get("field") or "").lower()
            if field == "assignee":
                assignee_events.append(
                    (
                        created,
                        item.get("fromString") or item.get("from_string"),
                        item.get("toString") or item.get("to_string"),
                    )
                )
            if field == "status":
                to_status = (item.get("toString") or item.get("to_string") or "").casefold()
                if to_status == "in progress" and author:
                    in_progress_authors.append((created, author))

    assignee_events.sort(key=lambda x: x[0])
    in_progress_authors.sort(key=lambda x: x[0])

    # Build assignee timeline durations
    timeline: list[tuple[datetime, str | None]] = []
    for created, _from_name, to_name in assignee_events:
        timeline.append((created, to_name))

    now = datetime.now(timezone.utc)
    durations: dict[str, float] = {}
    for index, (start, name) in enumerate(timeline):
        if not name:
            continue
        end = timeline[index + 1][0] if index + 1 < len(timeline) else now
        seconds = max(0.0, (end - start).total_seconds())
        durations[name] = durations.get(name, 0.0) + seconds

    def is_qa(name: str | None) -> bool:
        return matches_name(name, qa)

    # Candidate A: walk assignees newest → oldest, first non-QA
    ordered_names: list[str] = []
    if current_assignee:
        ordered_names.append(current_assignee)
    for _created, _from_name, to_name in reversed(assignee_events):
        if to_name and to_name not in ordered_names:
            ordered_names.append(to_name)
        if _from_name and _from_name not in ordered_names:
            ordered_names.append(_from_name)

    candidate_a = next((n for n in ordered_names if not is_qa(n)), None)

    # Candidate B: In Progress author if non-QA, else longest non-QA assignee
    candidate_b = None
    method_b = ""
    for _ts, author in reversed(in_progress_authors):
        if not is_qa(author):
            candidate_b = author
            method_b = "in_progress_author"
            break
    if candidate_b is None and durations:
        ranked = sorted(
            ((name, secs) for name, secs in durations.items() if not is_qa(name)),
            key=lambda x: x[1],
            reverse=True,
        )
        if ranked:
            candidate_b = ranked[0][0]
            method_b = "longest_assignee"

    if candidate_b and candidate_a and candidate_b == candidate_a:
        return OwnershipResult(candidate_a, "agree", "", platform)
    if candidate_b:
        note = f"fallback_a={candidate_a}" if candidate_a and candidate_a != candidate_b else ""
        return OwnershipResult(candidate_b, method_b or "candidate_b", note, platform)
    if candidate_a:
        return OwnershipResult(candidate_a, "pre_qa_assignee", "", platform)
    return OwnershipResult(None, "unknown", "no_non_qa_assignee", platform)
