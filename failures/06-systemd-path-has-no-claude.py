#!/usr/bin/env python3
"""Smaller one: systemd's PATH.

User units get the service manager's PATH, which had no ~/.local/bin. Under a timer `claude`
was not found, while from a terminal the same lane ran.

Real here: bin/lane-run.sh, run end to end. Simulated: systemd's environment and the claude
binary. The runner is started with a bare environment whose PATH holds only the basic tools
(symlinked into a temp folder) and a HOME whose ~/.local/bin has a stand-in `claude` that wraps
tests/fake-claude. A real claude on this machine can never be found by this script.

Guardrail: bin/lane-run.sh exports PATH="$here:$HOME/.local/bin:$PATH" before it starts claude,
which also puts bin/ on PATH so a lane prompt can call `lanes deliver`.
Guarding test: none in tests/ before this folder (the runner tests pass LANE_CLAUDE_BIN, which
skips the PATH lookup); tests/test_failures.py runs this script.
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
TOOLS = ("bash", "sh", "env", "python3", "flock", "timeout", "date", "mkdir", "cat", "tail", "tee",
         "dirname", "basename", "readlink", "sleep", "awk")


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-06-"))
    atexit.register(shutil.rmtree, tmp, True)
    sysbin, home, lanes = os.path.join(tmp, "sysbin"), os.path.join(tmp, "home"), os.path.join(tmp, "lanes")
    localbin = os.path.join(home, ".local", "bin")
    for d in (sysbin, localbin, lanes):
        os.makedirs(d)
    for tool in TOOLS:
        found = shutil.which(tool)
        if not found:
            print(f"FAIL: this machine has no {tool}; the runner needs it")
            return 1
        os.symlink(found, os.path.join(sysbin, tool))
    seen = os.path.join(tmp, "lanes-on-path.txt")
    claude = os.path.join(localbin, "claude")
    with open(claude, "w") as f:
        f.write(f"#!/bin/sh\ncommand -v lanes > '{seen}' || echo missing > '{seen}'\nexec '{FAKE}' \"$@\"\n")
    os.chmod(claude, os.stat(claude).st_mode | stat.S_IXUSR)
    with open(os.path.join(lanes, "demo.md"), "w") as f:
        f.write("You are a test lane called demo.\n")

    # What a user unit gets: the manager's PATH, nothing from a login shell.
    env = {"PATH": sysbin, "HOME": home, "LANES_DB": os.path.join(tmp, "lanes.db"), "LANES_DIR": lanes,
           "LANES_LOG_DIR": os.path.join(tmp, "logs"), "LANE_SKIP_LOGIN_CHECK": "1", "FAKE_CLAUDE_SLEEP": "0.1"}
    print(f"setup: PATH={sysbin} (basic tools only), and claude lives in {localbin}")

    p = subprocess.run(["sh", "-c", "command -v claude"], env=env, capture_output=True, text=True)
    print(f"without the guardrail: `command -v claude` with that PATH exits {p.returncode}, "
          "so a runner that trusts PATH can't start the lane")

    held = True
    p = subprocess.run([os.path.join(sysbin, "bash"), RUNNER, "main", "demo"], env=env,
                       capture_output=True, text=True, timeout=60)
    db = sqlite3.connect(env["LANES_DB"])
    row = db.execute("select status from lane_runs").fetchone()
    db.close()
    print(f"guardrail: lane-run.sh exited {p.returncode}; the run log says {row[0] if row else 'nothing'}")
    if p.returncode != 0 or not row or row[0] != "ok":
        print(f"FAIL: the lane did not run under the bare PATH\n{p.stdout}{p.stderr}")
        held = False
    on_path = open(seen).read().strip() if os.path.exists(seen) else "missing"
    print(f"guardrail: inside the lane, `lanes` resolves to {on_path}")
    if on_path == "missing" or os.path.realpath(on_path) != os.path.join(ROOT, "bin", "lanes"):
        print("FAIL: a lane prompt could not call `lanes deliver`")
        held = False

    print("HELD: the runner finds claude and lanes with systemd's bare PATH" if held else
          "BROKEN: under a bare PATH the lane could not start, or could not reach `lanes`")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
