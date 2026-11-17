#!/usr/bin/env python3
"""Failure 5: agents left files nobody tracked.

Lanes left reports, drafts and batches in folders, and nothing recorded what had been made or
whether anyone had read it.

Real here: deliver(), lint() and `lanes nightly` in bin/lanes, on a temp database and a temp
output folder. Simulated: the agent. It is this script writing a file and "forgetting" to
register it.

Guardrail: stray_files() and the deleted-file check in lint(), both in bin/lanes; cmd_nightly()
turns the warnings into one inbox row with no agent involved.
Guarding tests: tests/test_lint.py, Lint.test_a_file_nothing_registered_is_flagged_until_it_is_delivered,
Lint.test_a_row_whose_file_is_gone_is_flagged and Sweep.test_the_nightly_report_is_one_row_however_often_it_warns.
"""
import atexit
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.dont_write_bytecode = True


def load_lanes():
    loader = SourceFileLoader("lanes_core", os.path.join(ROOT, "bin", "lanes"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("lanes_core", loader))
    loader.exec_module(mod)
    return mod


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-05-"))
    atexit.register(shutil.rmtree, tmp, True)
    out, lanes = os.path.join(tmp, "outbox"), os.path.join(tmp, "lanes")
    os.makedirs(out), os.makedirs(lanes)
    with open(os.path.join(lanes, "lanes.toml"), "w") as f:
        f.write(f'[inbox]\nroots = ["{out}"]\n')
    os.environ.update(LANES_DB=os.path.join(tmp, "lanes.db"), LANES_DIR=lanes, LANES_LOG_DIR=os.path.join(tmp, "logs"))
    core = load_lanes()
    db = core.connect()

    def warnings(word):
        return [line for sev, line in core.lint(db) if sev == "warn" and word in line]

    # The agent writes a draft and never registers it.
    draft = os.path.join(out, "partner-pitch-draft.md")
    with open(draft, "w") as f:
        f.write("Hi, I run a bike shop app (example)...\n")
    rows = db.execute("select count(*) from deliverables").fetchone()[0]
    print(f"without the guardrail: {draft} exists and the inbox has {rows} rows; nobody knows it is waiting")

    held = True
    stray = warnings("have no row")
    print(f"guardrail: lint says: {stray[0] if stray else '(nothing)'}")
    if not stray:
        print("FAIL: lint did not notice the unregistered file")
        held = False

    with contextlib.redirect_stdout(io.StringIO()):
        core.main(["nightly"])
    night = db.execute("select title, needs from deliverables where source = 'nightly'").fetchall()
    print(f"guardrail: the nightly run, with no agent, put this in the inbox: "
          f"{', '.join(f'{r[0]} ({r[1]})' for r in night) or '(nothing)'}")
    if len(night) != 1 or night[0]["needs"] != "act":
        print("FAIL: the nightly run did not leave one row that needs a human")
        held = False

    core.deliver(db, "outreach", "draft", draft, title="Partner pitch draft")
    if warnings("have no row"):
        print("FAIL: lint still flags the file after it was registered")
        held = False
    else:
        print("control: once registered with deliver(), the file is no longer flagged")

    os.remove(draft)
    gone = warnings("no longer exists")
    print(f"guardrail: after the file is deleted, lint says: {gone[0] if gone else '(nothing)'}")
    if not gone:
        print("FAIL: lint did not notice an inbox row whose file is gone")
        held = False

    print("HELD: a file nothing registered, or a row whose file is gone, reaches a human" if held else
          "BROKEN: an untracked file or a dead row went unnoticed")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
