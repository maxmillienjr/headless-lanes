#!/usr/bin/env python3
"""SessionStart hook: what is waiting, printed where an interactive session will see it.

An interactive Claude Code session starts blind to what the headless lanes did overnight.
This prints three short things at session start: inbox rows that need the human, decisions
waiting in the queue, and lint warnings. The session then knows what is open before the first
message.

Two rules, both from things that went wrong:
  - It never blocks a session. Any failure prints one line and exits 0.
  - It never creates a database. On a machine with no database it says so and stops. (A hook
    that "helpfully" connected once created an empty second database on a laptop.)

Wire it up in the project's .claude/settings.json:

  {"hooks": {"SessionStart": [{"hooks": [
    {"type": "command", "command": "python3 ~/headless-lanes/hooks/session-digest.py", "timeout": 10}
  ]}]}}
"""
import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CONSOLE = os.environ.get("LANES_CONSOLE_URL", "http://127.0.0.1:8787")
SHOW = 6


def main():
    sys.dont_write_bytecode = True
    loader = SourceFileLoader("lanes_core", os.path.join(ROOT, "bin", "lanes"))
    core = importlib.util.module_from_spec(importlib.util.spec_from_loader("lanes_core", loader))
    loader.exec_module(core)
    if not os.path.isfile(core.db_path()):
        print(f"(lanes digest skipped: no database at {core.db_path()} on this machine)")
        return
    db = core.connect()
    need = core.needs_you(db)
    unread = db.execute("select count(*) from deliverables where status = 'unread'").fetchone()[0]
    todo = db.execute("select * from decisions where state = 'todo' order by id").fetchall()
    warns = [line for sev, line in core.lint(db) if sev == "warn"]
    print(f"Inbox: {len(need)} need you ({unread} unread). {CONSOLE}/inbox")
    for r in need[:SHOW]:
        print(f"  [{r['lane']}/{r['kind']}] {r['date']} {r['title']}  ({CONSOLE}/d/{r['id']})")
    print(f"Queue: {len(todo)} decision(s) waiting on a human. {CONSOLE}/queue")
    for d in todo[:SHOW]:
        print(f"  D-{d['id']} [{d['label']}] {d['title']}")
    if warns:
        print(f"Lint: {len(warns)} warning(s).")
        for line in warns[:SHOW]:
            print(f"  {line}")
    print("Register anything you make for the human with `lanes deliver <lane> <kind> <path|url> title=...` "
          "in the same step. File a decision only when a human must decide.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as e:  # never block session start (connect() can refuse with SystemExit)
        print(f"(lanes digest skipped: {type(e).__name__}: {e})")
