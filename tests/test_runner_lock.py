"""bin/lane-run.sh against a stand-in for the claude binary: the seat lock, the run log, the
failure path, and the environment a lane runs in."""
import os
import subprocess
import time
import unittest

from support import ROOT, LanesCase, core

RUNNER = os.path.join(ROOT, "bin", "lane-run.sh")


class Runner(LanesCase):
    def setUp(self):
        super().setUp()
        for lane in ("daily", "weekly", "by-hand"):
            with open(os.path.join(os.environ["LANES_DIR"], lane + ".md"), "w") as f:
                f.write(f"You are a test lane called {lane}.\n")
        self.env = {**os.environ, "LANE_CLAUDE_BIN": os.path.join(ROOT, "tests", "fake-claude"),
                    "LANE_SKIP_LOGIN_CHECK": "1", "FAKE_CLAUDE_SLEEP": "0.2", "ANTHROPIC_API_KEY": "sk-should-not-leak"}

    def start(self, seat, lane, **env):
        return subprocess.Popen([RUNNER, seat, lane], env={**self.env, **env}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)

    def runs(self):
        return self.db.execute("select * from lane_runs order by id").fetchall()

    def wait_for_lock(self, seat):
        """Block until a run on `seat` has started (its log file exists, so it holds the lock)."""
        folder = os.path.join(os.environ["LANES_LOG_DIR"], seat)
        for _ in range(100):
            if os.path.isdir(folder) and any(n.endswith(".json") for n in os.listdir(folder)):
                return
            time.sleep(0.05)
        self.fail("the first run never started")

    def test_a_second_run_on_the_same_seat_is_refused(self):
        first = self.start("main", "daily", FAKE_CLAUDE_SLEEP="2")
        self.wait_for_lock("main")
        second = self.start("main", "weekly", LANE_LOCK_WAIT="1")
        out = second.communicate(timeout=20)[0]
        self.assertEqual(second.returncode, 75)
        self.assertIn("seat main is busy", out)
        self.assertEqual(first.wait(timeout=20), 0)
        rows = {r["lane"]: r["status"] for r in self.runs()}
        self.assertEqual(rows, {"weekly": "locked", "daily": "ok"})
        inbox = self.db.execute("select title, needs from deliverables").fetchall()
        self.assertEqual(len(inbox), 1)
        self.assertTrue(inbox[0]["title"].startswith("Lane failed: weekly (locked"))
        self.assertEqual(inbox[0]["needs"], "act")
        first.stdout.close()

    def test_a_second_run_waits_its_turn_when_given_time(self):
        first = self.start("main", "daily", FAKE_CLAUDE_SLEEP="1")
        self.wait_for_lock("main")
        second = self.start("main", "weekly", LANE_LOCK_WAIT="20")
        self.assertEqual((first.wait(timeout=20), second.wait(timeout=20)), (0, 0))
        first.stdout.close(), second.stdout.close()
        a, b = self.runs()
        self.assertEqual((a["lane"], a["status"], b["lane"], b["status"]), ("daily", "ok", "weekly", "ok"))
        self.assertGreaterEqual(b["started"], a["ended"])       # one after the other, never together

    def test_another_seat_is_not_blocked(self):
        first = self.start("main", "daily", FAKE_CLAUDE_SLEEP="2")
        self.wait_for_lock("main")
        second = self.start("other", "by-hand", LANE_LOCK_WAIT="1")
        self.assertEqual(second.wait(timeout=20), 0)
        self.assertIsNone(first.poll())                          # the first is still running
        self.assertEqual(first.wait(timeout=20), 0)
        first.stdout.close(), second.stdout.close()

    def test_the_run_bills_the_seat_not_an_api_key(self):
        p = self.start("other", "by-hand", LANE_INPUT="D-4: 1 3")
        self.assertEqual(p.wait(timeout=20), 0)
        p.stdout.close()
        r = self.runs()[0]
        self.assertIn("api_key=unset", r["summary"])            # ANTHROPIC_API_KEY was set in our env
        self.assertIn("seat_dir=.claude-other", r["summary"])    # the seat's own login
        self.assertIn("caller_input=yes", r["summary"])          # LANE_INPUT reached the prompt
        self.assertEqual((r["turns"], r["input_tokens"], r["output_tokens"]), (7, 1200, 300))
        self.assertTrue(os.path.isfile(os.path.expanduser(r["log"])))

    def test_a_failed_run_is_logged_and_put_in_the_inbox(self):
        p = self.start("main", "daily", FAKE_CLAUDE_FAIL="1")
        self.assertNotEqual(p.wait(timeout=20), 0)
        p.stdout.close()
        self.assertEqual([r["status"] for r in self.runs()], ["error"])
        row = self.db.execute("select * from deliverables").fetchone()
        self.assertEqual((row["lane"], row["kind"], row["needs"], row["status"]), ("ops", "report", "act", "unread"))
        self.assertTrue(any("ended error" in line for sev, line in core.lint(self.db)))

    def test_refuses_a_bad_name_before_touching_anything(self):
        for seat, lane in (("main", "../etc"), ("Bad Seat", "daily")):
            p = self.start(seat, lane)
            self.assertEqual(p.wait(timeout=20), 2)
            p.stdout.close()
        self.assertEqual(self.runs(), [])

    def test_a_run_that_cannot_start_still_gets_a_row(self):
        p = self.start("main", "nope")                           # no lanes/nope.md
        self.assertEqual(p.wait(timeout=20), 2)
        p.stdout.close()
        p = self.start("main", "daily", LANE_SKIP_LOGIN_CHECK="", HOME=self.tmp)   # seat never logged in
        self.assertEqual(p.wait(timeout=20), 3)
        p.stdout.close()
        self.assertEqual([(r["lane"], r["status"]) for r in self.runs()], [("nope", "error"), ("daily", "error")])
        self.assertEqual(self.db.execute("select count(*) from deliverables where needs = 'act'").fetchone()[0], 2)

    def test_something_the_agent_left_running_does_not_hold_the_seat(self):
        first = self.start("main", "daily", FAKE_CLAUDE_ORPHAN="6")
        self.assertEqual(first.wait(timeout=20), 0)              # the run is over, its child is not
        second = self.start("main", "weekly", LANE_LOCK_WAIT="1")
        self.assertEqual(second.wait(timeout=20), 0)
        first.stdout.close(), second.stdout.close()
        self.assertEqual([r["status"] for r in self.runs()], ["ok", "ok"])

    def test_the_kill_switch_skips_the_run(self):
        stop = os.path.join(self.tmp, "daily.STOP")
        open(stop, "w").close()
        p = self.start("main", "daily")
        out = p.communicate(timeout=20)[0]
        self.assertEqual(p.returncode, 0)
        self.assertIn("kill switch is on", out)
        self.assertEqual(self.runs(), [])                        # no seat woken, no row
        self.assertTrue(any("kill switch is on for daily" in line for sev, line in core.lint(self.db)))
        p = self.start("main", "weekly")                         # another lane is not paused
        self.assertEqual(p.wait(timeout=20), 0)
        p.stdout.close()
        os.rename(stop, os.path.join(self.tmp, "STOP"))          # the global switch pauses everything
        p = self.start("main", "weekly")
        self.assertEqual(p.wait(timeout=20), 0)
        p.stdout.close()
        self.assertEqual(len(self.runs()), 1)


if __name__ == "__main__":
    unittest.main()
