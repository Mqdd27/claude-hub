---
name: claude-context
description: Use when the user asks what they worked on, the status/history of one of their projects, past decisions, or wants a repo/code check informed by their Claude Code sessions from their Mac.
version: 1.0.0
platforms: [linux]
---

# Claude Code context (from the user's Mac)

The user codes on a Mac with Claude Code. Every session is synced to this server and
digested into small markdown files, refreshed every ~5 minutes while the Mac is online.

## Where things are

- `~/claude-hub/digest/INDEX.md`: **start here.** One line per session, newest first:
  `date | project | title | file`
- `~/claude-hub/digest/<project>/<date>_<sid8>.md`: one session. Header (project, date, cwd, branch,
  session id), then `**User:**` / `**Claude:**` turns. Tool calls appear as one line: `🔧 Tool: what it did`.
  Tool outputs are not included.
- `~/claude-hub/ctx/<absolute Mac path>/CLAUDE.md`: project instructions, only for projects that have one
  (the session header's `cwd` is that path).
- `~/claude-hub/data/`: raw JSONL (hundreds of MB). **Do not read it.** Use the digest.

## How to answer

1. Read `INDEX.md` (or `grep "| <project> |" ~/claude-hub/digest/INDEX.md`) to find the right sessions by date and project.
2. Search across sessions: `grep -ril "<keyword>" ~/claude-hub/digest/<project>/`
3. Open only the files you need. Big files: `grep -n` first, then read only the relevant part.
4. For code or commits, use GitHub (code is not on this server):
   - Find the repo: a github.com URL inside the digest, or `gh repo list` (own account) and
     `gh repo list <org>` for each org in `gh org list`. Repos often live in an org, not the personal account.
   - `gh api repos/<owner>/<repo>/commits?since=<ISO date>`, `gh pr list -R <owner>/<repo>`, or the GitHub MCP tools.
5. Note that the session only shows what was discussed. Check commits for what actually shipped.

## Rules

- Read-only. Never modify `~/claude-hub/`, and never push or comment on GitHub unless the user asks.
- `[REDACTED]` marks a removed secret. Never try to recover it, and never quote anything that looks like a credential.
- Cite sources: the digest path and/or commit SHA.
- Project names are the last part of the session's `cwd`. A session started in the home folder shows up
  under the Mac username, and one started in a parent folder (for example `projects`) covers several projects.
