# claude-hub

Give your always-on AI agents (e.g. [nanobot](https://github.com/HKUDS/nanobot), [Hermes Agent](https://github.com/nousresearch/hermes-agent)) the context of
your [Claude Code](https://docs.claude.com/en/docs/claude-code) sessions.

```
Mac (unchanged)                      Server
~/.claude/projects/*.jsonl  ─rsync─▶ ~/claude-hub/data/      (raw history, archive)
~/Documents/**/CLAUDE.md    ─rsync─▶ ~/claude-hub/ctx/       (project instructions)
                                          │ digest.py, every 5 min
                                          ▼
                                     ~/claude-hub/digest/INDEX.md + <project>/<date>_<id>.md
                                          ▲
                        skill/claude-context/SKILL.md  ◀── linked into each agent's skills
```

- **One-way.** The Mac only pushes. Nothing on the server can write back to the Mac.
- **Small.** The digest keeps user prompts, Claude's replies, and one line per tool call. Tool output and
  thinking are dropped. In practice 645 MB of JSONL becomes about 4 MB.
- **Redacted.** Common secret shapes (`sk-…`, `ghp_…`, `AKIA…`, JWTs, `Bearer …`, `*_KEY=`/`"secret": "…"`)
  become `[REDACTED]`. This is pattern-based, so treat the digest as sensitive anyway.
- **No code is copied.** Agents read code from GitHub (`gh` / GitHub MCP) on their own.
- **Excludes.** Folders listed in `EXCLUDE_DIRS`.

## Requirements

- Mac with Claude Code, `/usr/bin/rsync`, key-based SSH to the server
- Linux server with `python3` (stdlib only), `systemd --user`, and lingering enabled
  (`sudo loginctl enable-linger $USER`)
- Optional: agents whose skills use the `SKILL.md` format (nanobot, Hermes, …), and `gh` logged in on the server

## Setup

1. `cp config.env.example config.env` and edit it (server, excludes, skill folders).
2. **Full Disk Access for rsync.** macOS blocks launchd jobs from reading `~/Documents`.
   Open System Settings → Privacy & Security → Full Disk Access → **+**, press `Cmd+Shift+G`,
   enter `/usr/bin/rsync`, and add it.
3. `./install.sh`

The script is safe to re-run. Run it again after editing `config.env`, `digest.py`, or the skill.
It does the following:

- **Server:** copies `digest.py` and `skill/`, installs the `claude-digest.timer` user unit, and links the
  skill into every folder in `SKILL_DIRS` that exists.
- **Mac:** writes and loads two launchd agents, `claude-hub.history` and `claude-hub.ctx`. Each one runs
  `/usr/bin/rsync` directly every `INTERVAL` seconds. Running rsync directly, not through a shell
  script, is what lets the Full Disk Access grant apply.

## Check it works

```bash
launchctl list | grep claude-hub              # exit status 0 for both
cat /tmp/claude-hub-history.log /tmp/claude-hub-ctx.log   # empty = fine
ssh $SERVER 'head ~/claude-hub/digest/INDEX.md'
```

Then ask an agent: *"use skill claude-context: what did I work on yesterday?"* It should cite digest files.

`python3 digest.py --check` runs the self-test (tool output dropped, secrets redacted, incremental runs).

## Removing a folder after the fact

Add it to `EXCLUDE_DIRS`, run `./install.sh`, then delete what was already copied:

```bash
ssh $SERVER 'rm -rf ~/claude-hub/data/-Users-<you>-<path-with-dashes>* ~/claude-hub/digest/<project> && python3 ~/claude-hub/digest.py'
```

The history sync does not use `--delete`, on purpose: the server keeps sessions that Claude Code prunes locally.

## Usage

You can use this method to get a claude session from your mac into your "Server" with an agent on it, so the agent in your server can get those session context.

To check if it works try to ask to your agent:

``` text
Use skill claude-context: check what I was working on today on 'xxx' projects
```

## Uninstall

```bash
# Mac
launchctl unload ~/Library/LaunchAgents/claude-hub.*.plist && rm ~/Library/LaunchAgents/claude-hub.*.plist
# Server
systemctl --user disable --now claude-digest.timer
rm ~/.config/systemd/user/claude-digest.* ~/.nanobot/workspace/skills/claude-context ~/.hermes/skills/claude-context
rm -rf ~/claude-hub
```

## Security notes

- Anyone who can use your agents can read your coding history. Put the agents' web UIs behind
  authentication (for example, Cloudflare Access) or keep them on a private network (for example, Tailscale).
- The digest is sent to whatever LLM provider your agents use.
- Keep `config.env` out of git (it is in `.gitignore`).
