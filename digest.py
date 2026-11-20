#!/usr/bin/env python3
"""Turn Claude Code JSONL history into small, greppable markdown for agents (nanobot, Hermes).

Reads  $CLAUDE_HUB_DATA (default ~/claude-hub/data)  = synced copy of the Mac's ~/.claude/projects
Writes $CLAUDE_HUB_DIGEST (default ~/claude-hub/digest)/<project>/<date>_<sid8>.md + INDEX.md
Run: python3 digest.py        (incremental)   |   python3 digest.py --check   (self-test)
"""
import json, os, re, sys, tempfile

DATA = os.path.expanduser(os.environ.get("CLAUDE_HUB_DATA", "~/claude-hub/data"))
OUT = os.path.expanduser(os.environ.get("CLAUDE_HUB_DIGEST", "~/claude-hub/digest"))

# ponytail: pattern-based redaction only catches well-known secret shapes, not arbitrary passwords in prose
TOKENS = re.compile(
    r"sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[abpr]-[A-Za-z0-9\-]{10,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
)
ASSIGN = re.compile(r"(?i)(\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*['\"]?\s*[=:]\s*['\"]?|bearer\s+)[^\s'\",]{6,}")
NOISE = re.compile(r"<(system-reminder|local-command-stdout|local-command-caveat|command-[a-z]+)>.*?</\1>", re.S)


def redact(s):
    return ASSIGN.sub(r"\1[REDACTED]", TOKENS.sub("[REDACTED]", s))


def records(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                pass


def tool_line(b):
    i = b.get("input") or {}
    name = b.get("name", "?")
    arg = i.get("description") or i.get("file_path") or i.get("command") or i.get("pattern") or i.get("url") or i.get("prompt") or ""
    return f"🔧 {name}: {str(arg).splitlines()[0][:120] if arg else ''}"


def render(path):
    """Return (meta, markdown body) for one session file."""
    meta: dict = {"title": None, "cwd": None, "date": None, "branch": None, "first": None}
    lines = []
    for d in records(path):
        t = d.get("type")
        meta["cwd"] = meta["cwd"] or d.get("cwd")
        meta["branch"] = meta["branch"] or d.get("gitBranch")
        meta["date"] = meta["date"] or (d.get("timestamp") or "")[:10] or None
        if t == "ai-title":
            meta["title"] = d.get("aiTitle")
        if t not in ("user", "assistant") or d.get("isSidechain") or d.get("isMeta"):
            continue
        c = d.get("message", {}).get("content")
        blocks = [{"type": "text", "text": c}] if isinstance(c, str) else [b for b in c or [] if isinstance(b, dict)]
        texts, tools = [], []
        for b in blocks:
            if b.get("type") == "text":
                s = NOISE.sub("", b.get("text", "")).strip()
                if s:
                    texts.append(s)
            elif b.get("type") == "tool_use":
                tools.append(tool_line(b))
            # tool_result, thinking, images: dropped on purpose
        if texts:
            who = "**User:**" if t == "user" else "**Claude:**"
            lines.append(f"{who} " + "\n\n".join(texts))
            if t == "user" and not meta["first"]:
                meta["first"] = texts[0].splitlines()[0][:100]
        lines += tools
    meta["title"] = meta["title"] or meta["first"] or "(untitled)"
    return meta, redact("\n\n".join(lines))


def project_name(cwd, folder):
    return os.path.basename(cwd.rstrip("/")) if cwd else folder


def run(data=DATA, out=OUT):
    done = 0
    # sid8 -> mtime of its existing digest, so unchanged sessions are skipped without parsing
    seen = {f[-11:-3]: os.path.getmtime(os.path.join(r, f))
            for r, _, fs in os.walk(out) for f in fs if f.endswith(".md") and f != "INDEX.md"}
    for folder in os.listdir(data):
        fdir = os.path.join(data, folder)
        if not os.path.isdir(fdir) or "-private-" in folder:  # skip tmp/scratch sessions
            continue
        for f in os.listdir(fdir):
            if not f.endswith(".jsonl"):
                continue
            src, sid = os.path.join(fdir, f), f[:-6]
            if seen.get(sid[:8], 0) >= os.path.getmtime(src):
                continue
            meta, body = render(src)
            if not body.strip():
                continue
            proj = project_name(meta["cwd"], folder)
            dst = os.path.join(out, proj, f"{meta['date'] or 'unknown'}_{sid[:8]}.md")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            head = (f"# {meta['title']}\n\n- project: {proj}\n- date: {meta['date']}\n- cwd: {meta['cwd']}\n"
                    f"- branch: {meta['branch']}\n- session: {sid}\n- resume (on Mac): cd {meta['cwd']} && claude --resume {sid}\n\n---\n\n")
            with open(dst + ".tmp", "w") as fh:
                fh.write(head + body + "\n")
            os.replace(dst + ".tmp", dst)
            done += 1
    write_index(out)
    return done


def write_index(out):
    rows = []
    for proj in os.listdir(out):
        pdir = os.path.join(out, proj)
        if not os.path.isdir(pdir):
            continue
        for f in os.listdir(pdir):
            if f.endswith(".md"):
                with open(os.path.join(pdir, f)) as fh:
                    title = fh.readline()[2:].strip()
                rows.append((f[:10], proj, title, f"{proj}/{f}"))
    rows.sort(reverse=True)
    with open(os.path.join(out, "INDEX.md"), "w") as fh:
        fh.write("# Claude Code sessions (newest first)\n\ndate | project | title | file\n--- | --- | --- | ---\n")
        fh.writelines(f"{d} | {p} | {t.replace('|', '/')} | {path}\n" for d, p, t, path in rows)


def check():
    with tempfile.TemporaryDirectory() as tmp:
        data, out = os.path.join(tmp, "data"), os.path.join(tmp, "digest")
        os.makedirs(os.path.join(data, "-Users-x-proj"))
        recs = [
            {"type": "user", "cwd": "/Users/x/proj", "timestamp": "2026-11-20T01:00:00Z", "gitBranch": "main",
             "message": {"content": "fix login <system-reminder>noise</system-reminder> my key is sk-abcdefghijklmnopqrstuv"}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "SECRET_THOUGHT"},
                {"type": "text", "text": "Done. API_TOKEN=supersecret123 {\"tokenIssueSecret\": \"jsonsecret99\"}"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls", "description": "List files"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "HUGE_TOOL_OUTPUT"}]}},
            {"type": "ai-title", "aiTitle": "Fix login"},
        ]
        with open(os.path.join(data, "-Users-x-proj", "abcdef12-0000.jsonl"), "w") as fh:
            fh.write("\n".join(map(json.dumps, recs)))
        assert run(data, out) == 1
        md = open(os.path.join(out, "proj", "2026-11-20_abcdef12.md")).read()
        for bad in ("HUGE_TOOL_OUTPUT", "SECRET_THOUGHT", "noise", "sk-abcdef", "supersecret", "jsonsecret"):
            assert bad not in md, bad
        for good in ("# Fix login", "fix login", "🔧 Bash: List files", "API_TOKEN=[REDACTED]", "branch: main"):
            assert good in md, good
        assert "proj/2026-11-20_abcdef12.md" in open(os.path.join(out, "INDEX.md")).read()
        assert run(data, out) == 0  # incremental: nothing changed
    print("ok")


if __name__ == "__main__":
    check() if "--check" in sys.argv else print(f"digested {run()} sessions")
