"""Minimal Jira Cloud client for search + changelogs."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .credentials import jira_auth


class JiraClient:
    def __init__(self) -> None:
        base, user, token = jira_auth()
        self.base = base
        raw = f"{user}:{token}".encode()
        self._auth = base64.b64encode(raw).decode()

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base}{path}"
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Basic {self._auth}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"Jira {method} {path} failed: {exc.code} {detail}") from exc

    def search_issues(
        self,
        jql: str,
        fields: list[str],
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": max_results,
                "fields": fields,
            }
            if next_token:
                body["nextPageToken"] = next_token
            data = self._request("POST", "/rest/api/3/search/jql", body)
            batch = data.get("issues") or []
            issues.extend(batch)
            next_token = data.get("nextPageToken")
            if not next_token or not batch:
                break
        return issues

    def bulk_changelogs(
        self,
        issue_ids_or_keys: list[str],
        field_ids: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return map issueId -> changelog histories."""
        out: dict[str, list[dict[str, Any]]] = {}
        chunk_size = 40
        for i in range(0, len(issue_ids_or_keys), chunk_size):
            chunk = issue_ids_or_keys[i : i + chunk_size]
            body: dict[str, Any] = {
                "issueIdsOrKeys": chunk,
                "maxResults": 1000,
            }
            if field_ids:
                body["fieldIds"] = field_ids
            data = self._request("POST", "/rest/api/3/changelog/bulkfetch", body)
            for issue_change in data.get("issueChangeLogs") or []:
                issue_id = str(issue_change.get("issueId") or "")
                histories = issue_change.get("changeHistories") or []
                out.setdefault(issue_id, []).extend(histories)
            # Fallback pagination within chunk if needed
            while data.get("nextPageToken"):
                body["nextPageToken"] = data["nextPageToken"]
                data = self._request("POST", "/rest/api/3/changelog/bulkfetch", body)
                for issue_change in data.get("issueChangeLogs") or []:
                    issue_id = str(issue_change.get("issueId") or "")
                    histories = issue_change.get("changeHistories") or []
                    out.setdefault(issue_id, []).extend(histories)
        return out

    def issue_changelog(self, issue_key: str) -> list[dict[str, Any]]:
        start = 0
        histories: list[dict[str, Any]] = []
        while True:
            q = urllib.parse.urlencode({"startAt": start, "maxResults": 100})
            data = self._request("GET", f"/rest/api/3/issue/{issue_key}/changelog?{q}")
            values = data.get("values") or []
            histories.extend(values)
            if start + len(values) >= data.get("total", 0) or not values:
                break
            start += len(values)
        return histories
