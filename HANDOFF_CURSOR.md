# Handoff: trueid-assignee-report

Updated: 2026-10-22 (Asia/Bangkok)
Repo: `/Users/guyrocker/git/trueid-assignee-report`
Branch: `codex/assignee-report-platform-filter` (merged via PR #2)

## Goal

Report tickets + PRs for boards SC / IMP / LS / EXP / VAL.

## State

- Done: Root cause = wrong shell `JIRA_EMAIL`; fixed credentials to prefer mcp-atlassian pair.
- Done: Regenerated Jan–Oct with SC/IMP every month; stripped `jira_user` from published JSON.
- Done: `cpprm` — commit `5e1561e`, PR https://github.com/SebberSky/trueid-assignee-report/pull/2, merge pending verification in this turn.
- Optional leftover: full Bitbucket PR re-fetch; `trueid-android-v3-hero` still 404 for BB app password.

## Next actions

1. Confirm OpenAI site hosting picked up `dist/` from `main` after merge.
2. Optional: `python3 scripts/collect_report.py --month 2026-10` for fresh PR counts.
