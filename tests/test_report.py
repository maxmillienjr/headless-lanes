"""lanes report and its export: the weekly table, and the anonymised file a picture is made from."""
import datetime as dt
import json
import os
import re

from support import LanesCase, core

MONDAY = dt.datetime(2026, 3, 2)   # any Monday will do; the windows below are built from it


class Report(LanesCase):
    def at(self, seat, lane, start, secs, status="ok"):
        """One run that started at `start` and lasted `secs` (the stored duration is set wrong on
        purpose: the report must read the start and end stamps)."""
        rid = core.log_run(self.db, seat, lane, status, core.stamp(start),
                           core.stamp(start + dt.timedelta(seconds=secs)))[0]
        self.db.execute("update lane_runs set duration_s = 999999, cost_usd = 12.34, session_id = 'sess-secret', "
                        "summary = 'summary-secret', input_tokens = 4242 where id = ?", (rid,))
        self.db.commit()
        return rid

    def week(self):
        d = MONDAY
        self.at("main", "daily", d.replace(hour=6), 600)                          # Mon 06:00, 10 min
        self.at("main", "daily", d + dt.timedelta(days=1, hours=6), 300, "error")  # Tue, 5 min
        self.at("main", "weekly", d + dt.timedelta(days=2, hours=9), 1800, "timeout")
        self.at("main", "weekly", d + dt.timedelta(days=2, hours=9, minutes=40), 0, "locked")
        self.at("other", "by-hand", d + dt.timedelta(days=6, hours=23, minutes=59), 120)  # Sun 23:59
        self.at("other", "secret-lane", d + dt.timedelta(days=3, hours=12), 900)
        self.at("main", "daily", d - dt.timedelta(minutes=1), 60)                 # Sunday before: out
        self.at("main", "daily", d + dt.timedelta(days=7), 60)                    # next Monday 00:00: out

    def test_counts_and_minutes_per_seat_and_lane(self):
        self.week()
        rep = core.week_report(self.db, *core.week_window("2026-03-02"))
        seats = {s["seat"]: s for s in rep["seats"]}
        main = {ln["lane"]: ln for ln in seats["main"]["lanes"]}
        self.assertEqual((main["daily"]["runs"], main["daily"]["ok"], main["daily"]["failed"]), (2, 1, 1))
        self.assertEqual(main["daily"]["seconds"], 900)                       # from the stamps, not 999999
        self.assertEqual((main["weekly"]["failed"], main["weekly"]["locked"]), (1, 1))
        self.assertEqual(seats["main"]["total"]["minutes"], 45.0)
        self.assertEqual(seats["other"]["total"]["runs"], 2)
        self.assertEqual(rep["total"], {"runs": 6, "ok": 3, "failed": 2, "locked": 1, "seconds": 3720, "minutes": 62.0})

    def test_default_window_is_the_last_full_monday_to_sunday_week(self):
        for today, monday in (("2026-03-11T15:00", "2026-03-02"),    # a Wednesday
                              ("2026-03-09T00:30", "2026-03-02"),    # early on a Monday: last week, not this one
                              ("2026-03-08T23:59", "2026-02-23")):   # a Sunday: the week in progress is not full
            start, end = core.week_window(at=dt.datetime.fromisoformat(today))
            self.assertEqual(start, dt.datetime.fromisoformat(monday))
            self.assertEqual(end - start, dt.timedelta(days=7))

    def test_week_must_be_a_monday_and_days_is_a_rolling_window(self):
        with self.assertRaises(ValueError):
            core.week_window("2026-03-03")
        start, end = core.week_window(days=3, at=dt.datetime(2026, 3, 11, 12))
        self.assertEqual((start, end), (dt.datetime(2026, 3, 8, 12), dt.datetime(2026, 3, 11, 12)))

    def test_json_flag_prints_the_same_numbers(self):
        self.week()
        out = self.capture(["report", "--week", "2026-03-02", "--json"])
        self.assertEqual(json.loads(out), core.week_report(self.db, *core.week_window("2026-03-02")))

    def test_table_has_totals_and_no_money(self):
        self.week()
        out = self.capture(["report", "--week", "2026-03-02"])
        self.assertRegex(out, r"(?m)^total\s+6\s+3\s+2\s+1\s+62\.0\s+1h 02m$")
        self.assertNotIn("$", out)
        self.assertNotRegex(out.lower(), r"cost|usd|dollar|12\.34")

    def test_export_keeps_only_allowlisted_lanes_and_counts_the_rest(self):
        self.week()
        ex = self.export({"daily": "report", "weekly": "pipeline"})
        self.assertEqual(ex["lanes_shown"], 2)
        self.assertEqual(ex["runs_left_out"], 2)              # by-hand and secret-lane
        self.assertEqual(ex["seats"], ["seat 1"])             # the other seat had no allowlisted run
        self.assertEqual({r["kind"] for r in ex["runs"]}, {"report", "pipeline"})
        self.assertEqual(ex["totals"]["runs"], len(ex["runs"]))
        self.assertEqual(ex["totals"]["seconds"], sum(r["end_s"] - r["start_s"] for r in ex["runs"]))
        first = ex["runs"][0]
        self.assertEqual(first, {"seat": "seat 1", "kind": "report", "start_s": 6 * 3600, "end_s": 6 * 3600 + 600,
                                 "status": "ok"})

    def test_export_file_names_nothing_from_the_database(self):
        self.week()
        self.db.execute("update lane_runs set log = ?", (os.path.join(self.tmp, "logs", "main", "x.log"),))
        self.db.commit()
        path = os.path.join(self.tmp, "week.json")
        kinds = os.path.join(self.tmp, "kinds.toml")
        with open(kinds, "w") as f:
            f.write('[kinds]\ndaily = "report"\nweekly = "build"\nby-hand = "dispatcher"\n')
        self.capture(["report", "--week", "2026-03-02", "--export", path, "--kinds", kinds])
        text = open(path).read()
        for word in ("daily", "weekly", "by-hand", "secret", "main", "other", self.tmp, "x.log", "logs", "sess", "summary",
                     "4242", "token", "cost", "usd", "12.34", "$"):
            self.assertNotIn(word, text.lower(), word)
        self.assertEqual(json.loads(text)["seats"], ["seat 1", "seat 2"])

    def test_kinds_file_is_a_closed_allowlist(self):
        bad = os.path.join(self.tmp, "bad.toml")
        for body in ('[kinds]\ndaily = "daily"\n', '[kinds]\ndaily = "report"\n[extra]\nx = 1\n'):
            with open(bad, "w") as f:
                f.write(body)
            with self.assertRaises(ValueError):
                core.read_kinds(bad)

    def test_seed_with_a_fixed_clock_is_reproducible(self):
        a = self.seeded("a")
        b = self.seeded("b")
        self.assertEqual(a, b)
        self.assertEqual((a["runs"], a["failed"], a["locked"]), (15, 1, 1))

    # helpers
    def capture(self, argv):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(core.main(argv), 0)
        return buf.getvalue()

    def export(self, kinds):
        return core.week_export(self.db, *core.week_window("2026-03-02"), kinds)

    def seeded(self, name):
        root = os.path.join(self.tmp, name)
        saved = {k: os.environ[k] for k in ("LANES_DB", "LANES_DIR", "LANES_LOG_DIR")}
        os.environ.update(LANES_DB=os.path.join(root, "lanes.db"), LANES_DIR=os.path.join(root, "lanes"),
                          LANES_LOG_DIR=os.path.join(root, "logs"))
        try:
            db = core.seed_demo(root, dt.datetime(2026, 6, 1, 12))
            total = core.week_report(db, *core.week_window("2026-05-25"))["total"]
            db.close()
            return total
        finally:
            os.environ.update(saved)
