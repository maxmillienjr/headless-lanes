"""Shared test plumbing: load bin/lanes as a module and point it at a temp folder."""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ENV = ("LANES_DB", "LANES_DIR", "LANES_LOG_DIR", "LINEAR_API_KEY", "LINEAR_TEAM", "LANE_DISPATCH_QUIET_MIN")


def load(name, relpath):
    loader = SourceFileLoader(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


core = load("lanes_core", "bin/lanes")

TOML = """
[seats.main]
weekly_budget_min = 10
[seats.other]

[lanes.daily]
seat = "main"
cadence_days = 2
[lanes.weekly]
seat = "main"
cadence_days = 8
[lanes.by-hand]
seat = "other"

[inbox]
roots = ["{out}"]
"""


class LanesCase(unittest.TestCase):
    """Every test gets its own database, lanes folder and log folder."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lanes-test-")
        self.out = os.path.join(self.tmp, "outbox")
        self.saved = {k: os.environ.pop(k, None) for k in ENV}
        os.environ.update(LANES_DB=os.path.join(self.tmp, "lanes.db"), LANES_DIR=os.path.join(self.tmp, "lanes"),
                          LANES_LOG_DIR=os.path.join(self.tmp, "logs"))
        os.makedirs(self.out)
        os.makedirs(os.environ["LANES_DIR"])
        with open(os.path.join(os.environ["LANES_DIR"], "lanes.toml"), "w") as f:
            f.write(TOML.format(out=self.out))
        self.db = core.connect()

    def tearDown(self):
        self.db.close()
        for k, v in self.saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_row(self, lane, days_ago, status="ok", seat="main", secs=60):
        start = core.now() - core.dt.timedelta(days=days_ago)
        return core.log_run(self.db, seat, lane, status, core.stamp(start),
                            core.stamp(start + core.dt.timedelta(seconds=secs)))[0]

    def quiet(self, argv):
        """Run a CLI command in-process without its chatter in the test output."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return core.main(argv)

    def file(self, name, text="x"):
        p = os.path.join(self.out, name)
        with open(p, "w") as f:
            f.write(text)
        return p
