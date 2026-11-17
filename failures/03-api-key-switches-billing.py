#!/usr/bin/env python3
"""Failure 3: an API key in a shell rc file changed how everything was billed.

With ANTHROPIC_API_KEY set in the environment, Claude Code bills per token instead of using the
seat's subscription. A key left in a shell rc file reached every run started from that shell.

Real here: bin/lane-run.sh, run end to end against tests/fake-claude, which reports whether it
saw a key. Simulated: the key (an obviously fake value) and the claude binary. No network, and
no real seat is used.

Guardrail: bin/lane-run.sh starts claude with `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN`.
Guarding test: tests/test_runner_lock.py, Runner.test_the_run_bills_the_seat_not_an_api_key
(it checks ANTHROPIC_API_KEY). This script also checks ANTHROPIC_AUTH_TOKEN.
"""
import atexit
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RUNNER = os.path.join(ROOT, "bin", "lane-run.sh")
FAKE = os.path.join(ROOT, "tests", "fake-claude")


def shown(seen):
    """'ANTHROPIC_API_KEY=' (empty) reads better as 'ANTHROPIC_API_KEY=unset'."""
    return [s if s.endswith("=set") else s + "unset" for s in seen]


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-03-"))
    atexit.register(shutil.rmtree, tmp, True)
    lanes, spy_out = os.path.join(tmp, "lanes"), os.path.join(tmp, "seen-by-claude.txt")
    os.makedirs(lanes)
    with open(os.path.join(lanes, "demo.md"), "w") as f:
        f.write("You are a test lane called demo.\n")
    # A stand-in for claude that writes down which of the two variables it can see, then runs
    # the repo's own tests/fake-claude.
    spy = os.path.join(tmp, "claude-spy")
    with open(spy, "w") as f:
        f.write("#!/bin/sh\n"
                f"{{ echo \"ANTHROPIC_API_KEY=${{ANTHROPIC_API_KEY:+set}}\"; "
                f"echo \"ANTHROPIC_AUTH_TOKEN=${{ANTHROPIC_AUTH_TOKEN:+set}}\"; }} > '{spy_out}'\n"
                f"exec '{FAKE}' \"$@\"\n")
    os.chmod(spy, os.stat(spy).st_mode | stat.S_IXUSR)

    # The shell a timer or a terminal starts from, with a key left in its rc file.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp,
           "ANTHROPIC_API_KEY": "sk-ant-FAKE-0000-this-is-not-a-real-key",
           "ANTHROPIC_AUTH_TOKEN": "FAKE-token-not-real",
           "LANES_DB": os.path.join(tmp, "lanes.db"), "LANES_DIR": lanes,
           "LANES_LOG_DIR": os.path.join(tmp, "logs"), "LANE_CLAUDE_BIN": spy,
           "LANE_SKIP_LOGIN_CHECK": "1", "FAKE_CLAUDE_SLEEP": "0.1"}
    print("setup: ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are set (fake values) in the parent shell")

    # Without the guardrail: start claude straight from that shell.
    subprocess.run([spy, "-p", "hello"], env=env, capture_output=True, timeout=30)
    with open(spy_out) as f:
        seen = f.read().split()
    print(f"without the guardrail: claude started from that shell sees {' '.join(shown(seen))}")

    held = True
    p = subprocess.run([RUNNER, "main", "demo"], env=env, capture_output=True, text=True, timeout=60)
    with open(spy_out) as f:
        seen = f.read().split()
    print(f"guardrail: claude started by lane-run.sh sees {' '.join(shown(seen))}")
    if p.returncode != 0:
        print(f"FAIL: the run itself failed (exit {p.returncode}):\n{p.stdout}{p.stderr}")
        held = False
    if any(s.endswith("=set") for s in seen):
        print("FAIL: a key reached the lane, so this run would bill per token")
        held = False

    db = sqlite3.connect(env["LANES_DB"])
    row = db.execute("select status, summary from lane_runs").fetchone()
    db.close()
    print(f"run log: status {row[0] if row else None}, the stand-in reported: {row[1] if row else None}")
    if not row or "api_key=unset" not in (row[1] or ""):
        print("FAIL: the run log does not show an unset key")
        held = False

    print("HELD: a key in the parent environment never reaches a lane" if held else
          "BROKEN: a key in the parent environment reached the lane")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
