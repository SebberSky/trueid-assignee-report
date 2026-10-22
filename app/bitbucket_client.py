"""Bitbucket Cloud client for merged PR author counts."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import re
from collections import Counter, defaultdict
from typing import Any

from .credentials import bitbucket_auth

TICKET_RE = re.compile(r"\b(?:SC|IMP|LS|EXP|VAL)-\d+\b", re.IGNORECASE)


class BitbucketClient:
    def __init__(self) -> None:
        workspace, user, password = bitbucket_auth()
        self.workspace = workspace
        self._auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    def _get(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {self._auth}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())

    def count_merged_authors(
        self,
        repos: dict[str, str],
        start: str | None = None,
        end: str | None = None,
        pages_per_repo: int = 40,
        pagelen: int = 50,
    ) -> tuple[dict[str, Counter], dict[str, dict[str, str]]]:
        """Return (person -> Counter(platform -> count), ticket_key -> pr meta).

        PR meta keys: owner, platform, title, repo.
        """
        counts: dict[str, Counter] = defaultdict(Counter)
        ticket_meta: dict[str, dict[str, str]] = {}
        for repo, platform in repos.items():
            page = 1
            while page <= pages_per_repo:
                date_filter = ""
                if start and end:
                    date_filter = f' AND updated_on >= "{start}" AND updated_on < "{end}"'
                q = urllib.parse.urlencode(
                    {
                        "q": f'state = "MERGED"{date_filter}',
                        "pagelen": pagelen,
                        "page": page,
                        "fields": (
                            "values.author.display_name,values.title,values.description,"
                            "values.source.branch.name,size,next"
                        ),
                    }
                )
                url = (
                    "https://api.bitbucket.org/2.0/repositories/"
                    f"{self.workspace}/{repo}/pullrequests?{q}"
                )
                try:
                    data = self._get(url)
                except urllib.error.HTTPError as exc:
                    if exc.code in {403, 404}:
                        print(f"  skip repo {repo}: HTTP {exc.code} (no access)")
                        break
                    raise
                values = data.get("values") or []
                if not values:
                    break
                for item in values:
                    name = ((item.get("author") or {}).get("display_name")) or ""
                    if name:
                        counts[name][platform] += 1
                    title = item.get("title") or ""
                    description = item.get("description") or ""
                    branch = (((item.get("source") or {}).get("branch") or {}).get("name")) or ""
                    text = f"{title} {description} {branch}"
                    for key in TICKET_RE.findall(text):
                        ticket_key = key.upper()
                        # Last non-empty owner wins (matches prior overwrite behavior).
                        prev = ticket_meta.get(ticket_key) or {}
                        ticket_meta[ticket_key] = {
                            "owner": name or prev.get("owner") or "",
                            "platform": platform or prev.get("platform") or "",
                            "title": title or prev.get("title") or "",
                            "repo": repo or prev.get("repo") or "",
                        }
                if not data.get("next"):
                    break
                page += 1
        return counts, ticket_meta
