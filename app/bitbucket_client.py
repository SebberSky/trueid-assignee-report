"""Bitbucket Cloud client for merged PR author counts."""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
import re
from collections import Counter, defaultdict
from typing import Any

from .credentials import bitbucket_auth


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
    ) -> tuple[dict[str, Counter], dict[str, str]]:
        """person -> Counter(platform -> count)."""
        counts: dict[str, Counter] = defaultdict(Counter)
        ticket_owners: dict[str, str] = {}
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
                        "fields": "values.author.display_name,values.title,values.description,size,next",
                    }
                )
                url = (
                    "https://api.bitbucket.org/2.0/repositories/"
                    f"{self.workspace}/{repo}/pullrequests?{q}"
                )
                data = self._get(url)
                values = data.get("values") or []
                if not values:
                    break
                for item in values:
                    name = ((item.get("author") or {}).get("display_name")) or ""
                    if name:
                        counts[name][platform] += 1
                        text = f"{item.get('title') or ''} {item.get('description') or ''}"
                        for key in re.findall(r"\b(?:SC|IMP|LS|EXP|VAL)-\d+\b", text, re.IGNORECASE):
                            ticket_owners[key.upper()] = name
                if not data.get("next"):
                    break
                page += 1
        return counts, ticket_owners
