"""lint and the inbox sweep: the rules that run every night with no agent involved."""
import datetime as dt
import os
import time
import unittest

from support import LanesCase, core


class Lint(LanesCase):
    def lines(self):
        return [line for sev, line in core.lint(self.db) if sev == "warn"]

    def test_flags_a_lane_past_its_cadence(self):
        self.run_row("daily", 3)     # cadence 2 days: late
        self.run_row("weekly", 3)    # cadence 8 days: fine
        late = [line for line in self.lines() if "cadence" in line]
        self.assertEqual(len(late), 1)
        self.assertIn("lane daily", late[0])
        self.assertIn("2-day cadence", late[0])

    def test_a_lane_that_never_ran_is_flagged_but_a_by_hand_lane_is_not(self):
        text = "\n".join(self.lines())
        self.assertIn("lane daily: never run", text)
        self.assertIn("lane weekly: never run", text)
        self.assertNotIn("by-hand", text)   # no cadence_days: a quiet week is not a fault

    def test_only_an_ok_run_resets_the_cadence_clock(self):
        self.run_row("daily", 5)
        self.run_row("daily", 0, status="error")
        self.assertTrue(any("lane daily: last ok run" in line for line in self.lines()))

    def test_a_failed_run_counts_until_the_lane_recovers(self):
        self.run_row("daily", 1, status="timeout")
        self.assertTrue(any("ended timeout" in line for line in self.lines()))
        self.run_row("daily", 0)
        self.assertFalse(any("ended timeout" in line for line in self.lines()))

    def test_recovery_on_another_seat_does_not_clear_the_failure(self):
        self.run_row("daily", 1, status="error", seat="main")
        self.run_row("daily", 0, seat="other")
        self.assertTrue(any("lane daily on main ended error" in line for line in self.lines()))

    def test_seat_over_its_weekly_budget(self):
        self.run_row("daily", 0, secs=11 * 60)   # budget is 10 minutes
        self.assertTrue(any(line.startswith("seat main: 11 headless minutes") for line in self.lines()))

    def test_a_file_nothing_registered_is_flagged_until_it_is_delivered(self):
        p = self.file("report.md")
        self.assertTrue(any("have no row" in line for line in self.lines()))
        core.deliver(self.db, "ops", "report", p, title="A report")
        self.assertFalse(any("have no row" in line for line in self.lines()))

    def test_a_row_whose_file_is_gone_is_flagged(self):
        p = self.file("gone.md")
        core.deliver(self.db, "ops", "report", p)
        core.os.remove(p)
        self.assertTrue(any("no longer exists" in line for line in self.lines()))


class Sweep(LanesCase):
    def swept(self):
        return {rid: status for rid, status, _why, _title in core.sweep(self.db)}

    def test_fyi_clears_after_three_days_and_act_rows_stay(self):
        old = (dt.date.today() - dt.timedelta(days=4)).isoformat()
        fyi, _ = core.deliver(self.db, "ops", "digest", self.file("d.md"), date=old)
        act, _ = core.deliver(self.db, "ops", "draft", self.file("a.md"), date=old)
        fresh, _ = core.deliver(self.db, "ops", "digest", self.file("f.md"))
        self.assertEqual(self.swept(), {fyi: "read"})

    def test_a_row_follows_its_decision(self):
        did = core.add_decision(self.db, "ops", "Do the thing?")
        rid, _ = core.deliver(self.db, "ops", "draft", self.file("a.md"), decision=did)
        self.assertEqual(self.swept(), {})            # open decision: the row waits with it
        core.move(self.db, did, "decline")
        self.assertEqual(self.swept(), {rid: "superseded"})

    def test_expired_rows_clear(self):
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        rid, _ = core.deliver(self.db, "ops", "guide", self.file("g.md"), expires=yesterday)
        self.assertEqual(self.swept(), {rid: "read"})

    def test_delivering_the_same_path_twice_updates_one_row(self):
        p = self.file("a.md")
        first, what1 = core.deliver(self.db, "ops", "draft", p, title="v1")
        core.set_status(self.db, first, "read")
        second, what2 = core.deliver(self.db, "ops", "draft", p, title="v2")
        row = self.db.execute("select * from deliverables").fetchall()
        self.assertEqual((first, what1, what2, len(row)), (second, "added", "updated", 1))
        self.assertEqual((row[0]["title"], row[0]["status"]), ("v2", "unread"))   # regenerated = new reading

    def test_registering_again_without_a_title_keeps_the_title(self):
        p = self.file("digest.md")
        rid, _ = core.deliver(self.db, "product", "digest", p, title="Weekly digest", date="2026-01-05")
        did = core.add_decision(self.db, "product", "Rewrite the page?")
        core.deliver(self.db, "product", "digest", p, decision=did)          # the documented second step
        row = self.db.execute("select * from deliverables where id = ?", (rid,)).fetchone()
        self.assertEqual((row["title"], row["date"], row["decision"]), ("Weekly digest", "2026-01-05", f"D-{did}"))

    def test_the_nightly_report_is_one_row_however_often_it_warns(self):
        for _ in range(2):
            self.assertEqual(self.quiet(["nightly"]), 0)
        rows = self.db.execute("select needs from deliverables where source = 'nightly'").fetchall()
        self.assertEqual([r["needs"] for r in rows], ["act"])


class FailedUnit(LanesCase):
    def log(self, seat, name, age_min=0):
        folder = os.path.join(os.environ["LANES_LOG_DIR"], seat)
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, name)
        open(p, "w").close()
        when = time.time() - age_min * 60
        os.utime(p, (when, when))
        return p

    def registered(self):
        return [os.path.expanduser(r["path"]) for r in self.db.execute("select path from deliverables order by id")]

    def test_it_takes_this_lanes_fresh_log_and_no_other(self):
        self.log("main", "weekly-digest-20260105-060000.log")               # another lane with the same prefix
        mine = self.log("main", "weekly-20260105-060100.log")
        self.quiet(["failed", "lane-weekly.service"])
        self.assertEqual(self.registered(), [os.path.realpath(mine)])

    def test_with_no_fresh_log_it_leaves_a_note_instead_of_an_old_run(self):
        self.log("main", "weekly-20260101-060000.log", age_min=90)          # last week's run, which was fine
        self.quiet(["failed", "lane-weekly.service"])
        (path,) = self.registered()
        self.assertIn("unit-failures", path)
        with open(path) as f:
            self.assertIn("journalctl --user -u lane-weekly", f.read())


class Database(unittest.TestCase):
    MOUNTS = ("/dev/nvme0n1p2 / ext4 rw 0 0\n"
              "remote: /home/me/drive fuse.rclone rw 0 0\n"
              "tmpfs /tmp tmpfs rw 0 0\n")

    def test_knows_a_fuse_mount_from_a_local_disk(self):
        self.assertEqual(core.fs_type("/home/me/drive/lanes.db", self.MOUNTS), "fuse.rclone")
        self.assertEqual(core.fs_type("/home/me/.local/share/lanes.db", self.MOUNTS), "ext4")
        self.assertTrue(core.fs_type("/home/me/drive/x", self.MOUNTS).startswith(core.NETWORK_FS))


class SeedDemo(LanesCase):
    def test_it_refuses_to_write_outside_the_folder_it_was_given(self):
        other = os.path.join(self.tmp, "elsewhere")
        os.makedirs(other)
        with self.assertRaises(ValueError):
            core.seed_demo(other)                       # LANES_DB points at this test's database, not at `other`
        self.assertEqual(self.db.execute("select count(*) from lane_runs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
