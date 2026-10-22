"""Load Jira / Bitbucket credentials from env or Cursor mcp.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _mcp_env() -> dict[str, str]:
    path = Path.home() / ".cursor" / "mcp.json"
    if not path.exists():
        return {}
    cfg = json.loads(path.read_text())
    servers = cfg.get("mcpServers") or {}
    merged: dict[str, str] = {}
    for name, server in servers.items():
        lowered = str(name).lower()
        if not any(token in lowered for token in ("atlassian", "bitbucket", "jira")):
            continue
        env = (server or {}).get("env") or {}
        for key, value in env.items():
            if value and key not in merged:
                merged[key] = value
    return merged


def jira_auth() -> tuple[str, str, str]:
    env = {**_mcp_env(), **os.environ}
    base = (
        env.get("JIRA_BASE_URL")
        or env.get("JIRA_URL")
        or "https://truedmp.atlassian.net"
    ).rstrip("/")
    user = env.get("JIRA_EMAIL") or env.get("JIRA_USERNAME")
    token = env.get("JIRA_API_TOKEN")
    if not user or not token:
        raise RuntimeError("Missing JIRA_USERNAME/JIRA_EMAIL or JIRA_API_TOKEN")
    return base, user, token


def bitbucket_auth() -> tuple[str, str, str]:
    env = {**_mcp_env(), **os.environ}
    user = env.get("BITBUCKET_USERNAME")
    password = env.get("BITBUCKET_APP_PASSWORD")
    workspace = env.get("BITBUCKET_DEFAULT_WORKSPACE") or "truedmp"
    if not user or not password:
        raise RuntimeError("Missing BITBUCKET_USERNAME or BITBUCKET_APP_PASSWORD")
    return workspace, user, password
