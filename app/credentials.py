"""Load Jira / Bitbucket credentials from env or Cursor mcp.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _mcp_servers() -> dict[str, dict]:
    path = Path.home() / ".cursor" / "mcp.json"
    if not path.exists():
        return {}
    cfg = json.loads(path.read_text())
    return cfg.get("mcpServers") or {}


def _server_env(*name_tokens: str) -> dict[str, str]:
    """Return env from the first mcp server whose name matches any token."""
    for name, server in _mcp_servers().items():
        lowered = str(name).lower()
        if any(token in lowered for token in name_tokens):
            env = (server or {}).get("env") or {}
            return {k: v for k, v in env.items() if v}
    return {}


def _mcp_env() -> dict[str, str]:
    """Merged env from atlassian / bitbucket / jira MCP servers (first key wins)."""
    merged: dict[str, str] = {}
    for name, server in _mcp_servers().items():
        lowered = str(name).lower()
        if not any(token in lowered for token in ("atlassian", "bitbucket", "jira")):
            continue
        env = (server or {}).get("env") or {}
        for key, value in env.items():
            if value and key not in merged:
                merged[key] = value
    return merged


def jira_auth() -> tuple[str, str, str]:
    """Return (base_url, user, token).

    Prefer the coherent mcp-atlassian credential set. A shell ``JIRA_EMAIL`` that
    points at another account (e.g. Bitbucket user) can lack SC/IMP browse
    permission and silently return empty boards — do not let it override the
    Atlassian MCP pair unless ``JIRA_USE_ENV=1``.
    """
    mcp = _server_env("atlassian", "jira") or _mcp_env()
    use_env = os.environ.get("JIRA_USE_ENV", "").strip() in {"1", "true", "yes"}

    mcp_user = mcp.get("JIRA_USERNAME") or mcp.get("JIRA_EMAIL")
    mcp_token = mcp.get("JIRA_API_TOKEN")
    env_user = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USERNAME")
    env_token = os.environ.get("JIRA_API_TOKEN")
    base = (
        (os.environ.get("JIRA_BASE_URL") or os.environ.get("JIRA_URL") if use_env else None)
        or mcp.get("JIRA_BASE_URL")
        or mcp.get("JIRA_URL")
        or os.environ.get("JIRA_BASE_URL")
        or os.environ.get("JIRA_URL")
        or "https://truedmp.atlassian.net"
    )

    # Keep user+token as one source — never cross-pair mcp user with env token.
    if use_env and env_user and env_token:
        user, token = env_user, env_token
    elif (not use_env) and mcp_user and mcp_token:
        user, token = mcp_user, mcp_token
    elif env_user and env_token:
        user, token = env_user, env_token
    elif mcp_user and mcp_token:
        user, token = mcp_user, mcp_token
    else:
        raise RuntimeError("Missing JIRA_USERNAME/JIRA_EMAIL or JIRA_API_TOKEN")
    return base.rstrip("/"), user, token


def bitbucket_auth() -> tuple[str, str, str]:
    env = {**_mcp_env(), **os.environ}
    user = env.get("BITBUCKET_USERNAME")
    password = env.get("BITBUCKET_APP_PASSWORD")
    workspace = env.get("BITBUCKET_DEFAULT_WORKSPACE") or "truedmp"
    if not user or not password:
        raise RuntimeError("Missing BITBUCKET_USERNAME or BITBUCKET_APP_PASSWORD")
    return workspace, user, password
