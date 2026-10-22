# Jira Ownership Report

Local web report: per person, how many **tickets held** (iOS / Android) and how many **merged PRs** (iOS / Android / Mobile) across the 9 `/reviewpr` repos.

Ticket owner ignores QA closing assignees — uses last non-QA assignee before QA, or the person who moved the ticket to In Progress / held assignee longest.

## Setup

Credentials are read from `~/.cursor/mcp.json` (`mcp-atlassian` + `bitbucket` servers), with optional env override:

- Jira: prefers mcp-atlassian `JIRA_USERNAME` + `JIRA_API_TOKEN` (needed for SC / IMP browse access). Set `JIRA_USE_ENV=1` to force shell `JIRA_EMAIL` / `JIRA_API_TOKEN` instead.
- Bitbucket: `BITBUCKET_USERNAME` / `BITBUCKET_APP_PASSWORD` (env overrides mcp)

Boards: `SC` Social Commerce, `IMP` TrueID HERO, `LS` Watch, `EXP` Today, `VAL` DevEx.

## Collect

`data/*.json` is generated locally and **must not be committed**.

```bash
# Current month tickets + re-fetch PRs from Bitbucket (~2–3 min)
python3 scripts/collect_report.py --month 2026-10

# Or reuse a prior PR scan JSON
python3 scripts/collect_report.py --month 2026-10 \
  --prs-from /path/to/people_platforms_from_9repos.json
```

## View

Bind to localhost only (default). Open after collect:

```bash
python3 scripts/serve.py
# open http://127.0.0.1:8765/
```

## Config

- `config/qa_names.json` — QA excluded from ownership
- `config/exclude_names.json` — bots / noise
- `config/repos.json` — 9 repos → iOS / Android / Mobile
