#!/usr/bin/env python3
"""Failure 2: hooks crashed on a second machine and seeded an empty database.

I started using a second machine as a client. The session-start hooks crashed there, and a hook
that connected "helpfully" created an empty database on a machine that should have had none.

Real here: hooks/session-digest.py, run as a subprocess the way Claude Code runs a hook.
Simulated: the second machine. It is a temp folder with no database in it.

Guardrail: main() in hooks/session-digest.py checks os.path.isfile(core.db_path()) before it
connects, and its __main__ block turns any failure into one line and exit 0.
Guarding test: none in tests/ before this folder; tests/test_failures.py runs this script.
(The same manners in `lanes seed-demo` are covered by tests/test_lint.py, SeedDemo.)
"""
import atexit
import importlib.util
import os
import subprocess
import shutil
import sys
import tempfile
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "session-digest.py")
sys.dont_write_bytecode = True


def load_lanes():
    loader = SourceFileLoader("lanes_core", os.path.join(ROOT, "bin", "lanes"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("lanes_core", loader))
    loader.exec_module(mod)
    return mod


def hook(env):
    return subprocess.run([sys.executable, HOOK], env=env, capture_output=True, text=True, timeout=30)


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-02-"))
    atexit.register(shutil.rmtree, tmp, True)
    laptop = os.path.join(tmp, "second-machine")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "PYTHONDONTWRITEBYTECODE": "1",
           "LANES_DB": os.path.join(laptop, "lanes.db"), "LANES_DIR": os.path.join(laptop, "lanes"),
           "LANES_LOG_DIR": os.path.join(laptop, "logs")}
    print(f"setup: {laptop} stands in for a machine that has no database")

    # Without the guardrail: a hook that just calls connect() makes a database where there was none.
    os.environ.update(LANES_DB=os.path.join(tmp, "naive", "lanes.db"))
    core = load_lanes()
    db = core.connect()
    runs = db.execute("select count(*) from lane_runs").fetchone()[0]
    db.close()
    print(f"without the guardrail: connect() created {os.environ['LANES_DB']} with {runs} runs in it, "
          "and anything that reads it next sees an empty system, not a missing one")

    held = True
    p = hook(env)
    out = (p.stdout + p.stderr).strip()
    print(f"guardrail: the hook exited {p.returncode} and printed: {out}")
    if p.returncode != 0 or "no database" not in out:
        print("FAIL: the hook did not stop at the missing database")
        held = False
    if os.path.exists(env["LANES_DB"]):
        print(f"FAIL: the hook created {env['LANES_DB']}")
        held = False

    # A broken setup on a machine that does have a database still never blocks the session.
    os.makedirs(env["LANES_DIR"])
    os.environ.update(LANES_DB=env["LANES_DB"])
    core.connect().close()
    with open(os.path.join(env["LANES_DIR"], "lanes.toml"), "w") as f:
        f.write("[lanes.half-written\nseat = \n")
    p = hook(env)
    lines = (p.stdout + p.stderr).strip().splitlines()
    print(f"guardrail: with a broken lanes.toml the hook exited {p.returncode} with {len(lines)} line(s): "
          f"{lines[0] if lines else ''}")
    if p.returncode != 0 or len(lines) != 1 or "skipped" not in lines[0]:
        print("FAIL: a broken setup should degrade to one line and exit 0")
        held = False

    print("HELD: the hook never creates a database and never blocks a session" if held else
          "BROKEN: the hook created a database or blocked the session")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
