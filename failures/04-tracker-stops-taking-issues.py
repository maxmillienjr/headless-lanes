#!/usr/bin/env python3
"""Failure 4: the tracker's free plan stops creating issues past a cap.

Decisions were issues in a hosted tracker, and its free plan stops creating issues past a fixed
count of non-archived ones. A queue that stops accepting decisions is a bad way to fail.

Real here: add_decision(), mirror(), move() and dispatch_ready() in bin/lanes, with the Linear
mirror switched on. Simulated: the tracker. linear_gql() is swapped for a stand-in that refuses
every call the way a capped plan would, so nothing goes over the network and the key is fake.

Guardrail: the queue is the local `decisions` table; mirror() in bin/lanes catches any tracker
error, prints one warning and changes nothing locally. The rest of this guardrail is a practice
(closed issues auto-archive, no issue without a decision), and no script can check a practice.
Guarding test: tests/test_queue.py, Mirror.test_a_mirror_failure_never_blocks_the_local_write.
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


def capped(query, variables=None):
    raise RuntimeError("issue limit reached for this plan (simulated)")


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-04-"))
    atexit.register(shutil.rmtree, tmp, True)
    os.environ.update(LANES_DB=os.path.join(tmp, "lanes.db"), LANES_DIR=os.path.join(tmp, "lanes"),
                      LANES_LOG_DIR=os.path.join(tmp, "logs"), LINEAR_TEAM="OPS",
                      LINEAR_API_KEY="lin_api_FAKE_this_is_not_a_real_key")
    core = load_lanes()
    core.linear_gql = capped
    db = core.connect()
    print("setup: the tracker mirror is on, and the tracker refuses to create anything")

    # Without the guardrail: a queue that lives only in the hosted tracker.
    try:
        capped("mutation { issueCreate }")
    except RuntimeError as e:
        print(f"without the guardrail: filing the decision straight to the tracker fails ({e}), "
              "and the decision exists nowhere")

    held = True
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            did = core.add_decision(db, "ops", "Rewrite the pricing page?", "Approving means: a draft PR, nothing published.")
            core.move(db, did, "approve")
    except Exception as e:
        print(f"FAIL: the tracker's refusal reached the caller ({type(e).__name__}: {e}); "
              "an agent running `lanes queue add` would see its decision fail")
        print("BROKEN: a tracker refusal stopped the queue")
        return 1
    warnings = [line for line in err.getvalue().splitlines() if line]
    print(f"guardrail: D-{did} was filed and approved locally; the mirror said: {warnings[0] if warnings else '(nothing)'}")
    if not warnings or "mirror skipped" not in warnings[0]:
        print("FAIL: the mirror failed silently; a human would never learn the tracker is refusing")
        held = False
    ready = [d["id"] for d in core.dispatch_ready(db)]
    print(f"guardrail: dispatch-check would hand the dispatcher {', '.join(f'D-{i}' for i in ready) or 'nothing'}")
    if did not in ready:
        print("FAIL: the approved decision is not ready for the dispatcher")
        held = False

    print("HELD: the tracker refused and the queue kept working" if held else
          "BROKEN: a tracker refusal stopped the queue")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
