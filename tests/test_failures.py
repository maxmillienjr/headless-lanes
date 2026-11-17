"""failures/: every reproduction runs clean, says its guardrail held, and is in the folder's table."""
import glob
import os
import subprocess
import sys
import unittest

from support import ROOT

FOLDER = os.path.join(ROOT, "failures")
SCRIPTS = sorted(glob.glob(os.path.join(FOLDER, "[0-9][0-9]-*.py")))


class Reproductions(unittest.TestCase):
    def test_there_is_one_per_failure(self):
        self.assertGreaterEqual(len(SCRIPTS), 6)

    def test_every_guardrail_holds(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("LANES_", "LANE_", "LINEAR_", "ANTHROPIC_"))}
        for script in SCRIPTS:
            with self.subTest(script=os.path.basename(script)):
                p = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True, timeout=120)
                last = (p.stdout.strip().splitlines() or [""])[-1]
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertTrue(last.startswith("HELD: "), last)

    def test_the_readme_lists_every_script(self):
        with open(os.path.join(FOLDER, "README.md")) as f:
            readme = f.read()
        for script in SCRIPTS:
            self.assertIn(os.path.basename(script), readme)


if __name__ == "__main__":
    unittest.main()
