# Jira Ownership Report

Local web report: per person, how many **tickets held** (iOS / Android), total **ticket points**, and how many **merged PRs** (iOS / Android / Mobile) across the 9 `/reviewpr` repos.

Ticket owner ignores QA closing assignees — uses last non-QA assignee before QA, or the person who moved the ticket to In Progress / held assignee longest.
Ticket points use Jira Story Points (`customfield_10016`) and are summed by resolved ticket owner.
The published static bundle includes the generated files under `dist/data/`.

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

**Copy to Google Sheets** exports the selected month's table with the current
name, platform and board filters, then opens a blank Google Sheet for pasting.
If clipboard access is denied, the selected TSV remains visible for manual copy.

The separate **Export velocity report** button opens the prepared native Google
Sheet for the current year. It contains two tabs, **iOS** and **Android**, with
people under board section headings, Jan–Dec Jira points, and formula-based Q1–Q4
averages placed immediately after Mar, Jun, Sep and Dec. Board is a section heading,
not a repeated data column.
Missing/future months remain blank and are omitted from averages. The current
month uses the available report data. Excluded/QA owners follow the main report.
The page displays the export snapshot date; clicking opens that prepared report.
It does not refresh Jira or create another Drive file on each click.

To refresh the annual report after collecting monthly data:

1. Run `python3 scripts/prepare_velocity_report.py --refresh-points --output /absolute/output/velocity-data.json`.
   This reads `dist/data/`, including the latest month in `report.json`, and fills
   historical points from Jira without changing ownership or counting PRs.
2. Run `scripts/build_velocity_workbook.mjs` with the Codex bundled Node.js and
   `@oai/artifact-tool` runtime, passing the JSON and an output directory.
3. Import the verified workbook as a native Google Sheet with the connected
   Google Drive tool. Keep its existing access restrictions.
4. Update `dist/data/velocity-export.json` with the verified Sheet URL, year and
   snapshot timestamp, copy the UI to `dist/index.html`, and publish.

## Config

- `config/qa_names.json` — QA excluded from ownership
- `config/exclude_names.json` — bots / noise
- `config/repos.json` — 9 repos → iOS / Android / Mobile
