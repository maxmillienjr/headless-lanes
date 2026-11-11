"""The decision queue: state moves, and what dispatch-check hands a dispatcher."""
import contextlib
import io
import os
import subprocess
import sys
import unittest

from support import ROOT, LanesCase, core


class Moves(LanesCase):
    def state(self, did):
        return core.get_decision(self.db, did)["state"]

    def test_approve_is_the_only_way_into_in_progress(self):
        did = core.add_decision(self.db, "product", "Ship it?")
        self.assertEqual(self.state(did), "todo")
        self.assertEqual(core.move(self.db, did, "approve"), "in_progress")
        self.assertEqual(core.move(self.db, did, "hand-back", "Draft is ready.", "agent"), "todo")
        self.assertEqual(core.move(self.db, did, "approve"), "in_progress")
        self.assertEqual(core.move(self.db, did, "done", author="agent"), "done")

    def test_a_closed_decision_cannot_be_approved_until_reopened(self):
        did = core.add_decision(self.db, "product", "Ship it?")
        core.move(self.db, did, "decline", "No.")
        with self.assertRaises(ValueError):
            core.move(self.db, did, "approve")
        with self.assertRaises(ValueError):
            core.move(self.db, did, "hand-back")
        self.assertEqual(self.state(did), "declined")
        core.move(self.db, did, "reopen")
        self.assertEqual(core.move(self.db, did, "approve"), "in_progress")

    def test_ids_are_accepted_with_or_without_the_prefix(self):
        did = core.add_decision(self.db, "ops", "x")
        self.assertEqual(core.ident(f"D-{did}"), did)
        self.assertEqual(core.ident(str(did)), did)
        with self.assertRaises(ValueError):
            core.ident("nope")


class Dispatch(LanesCase):
    def ready(self, **kw):
        return [d["id"] for d in core.dispatch_ready(self.db, **kw)]

    def test_only_approved_decisions_are_ready(self):
        todo = core.add_decision(self.db, "product", "A")
        approved = core.add_decision(self.db, "product", "B")
        declined = core.add_decision(self.db, "product", "C")
        core.move(self.db, approved, "approve")
        core.move(self.db, declined, "decline")
        self.assertEqual(self.ready(), [approved])

    def test_label_filter(self):
        a = core.add_decision(self.db, "product", "A")
        b = core.add_decision(self.db, "ops", "B")
        core.move(self.db, a, "approve")
        core.move(self.db, b, "approve")
        self.assertEqual(self.ready(label="ops"), [b])
        self.assertEqual(self.ready(), [a, b])

    def test_an_answered_decision_waits_for_the_human_to_approve_again(self):
        did = core.add_decision(self.db, "product", "A")
        core.move(self.db, did, "approve")
        core.add_comment(self.db, did, "**Dispatch (main)** Done what I could. Your call on the rest.", "agent")
        self.assertEqual(self.ready(quiet_min=0), [])          # answered: not worked twice
        core.move(self.db, did, "approve", "Do the rest.")
        self.assertEqual(self.ready(quiet_min=0), [did])       # approved again: back in the list

    def test_continuing_keeps_it_in_the_list_after_the_quiet_window(self):
        did = core.add_decision(self.db, "product", "A")
        core.move(self.db, did, "approve")
        core.add_comment(self.db, did, "**Dispatch (main)** Half done. [continuing]", "agent")
        self.assertEqual(self.ready(), [])                     # an agent touched it under 20 minutes ago
        later = core.now() + core.dt.timedelta(minutes=21)
        self.assertEqual(self.ready(at=later), [did])

    def test_a_human_comment_does_not_hide_it(self):
        did = core.add_decision(self.db, "product", "A")
        core.move(self.db, did, "approve", "Picks: 1 3")
        self.assertEqual(self.ready(), [did])

    def test_cli_exit_code_is_the_exec_condition(self):
        cli = [sys.executable, os.path.join(ROOT, "bin", "lanes")]
        empty = subprocess.run(cli + ["dispatch-check", "product"], capture_output=True, text=True)
        self.assertEqual((empty.returncode, empty.stdout), (1, ""))     # nothing approved: wake no seat
        did = core.add_decision(self.db, "product", "A")
        core.move(self.db, did, "approve")
        full = subprocess.run(cli + ["dispatch-check", "product"], capture_output=True, text=True)
        self.assertEqual(full.returncode, 0)
        self.assertIn(f"D-{did}\t[product] A", full.stdout)

    def test_a_broken_setup_is_not_an_empty_queue(self):
        with open(os.path.join(os.environ["LANES_DIR"], "lanes.toml"), "w") as f:
            f.write("[lanes.broken\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "lanes"), "dispatch-check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 255)             # systemd fails the unit on 255; 1 would skip it


class LinearMirror(LanesCase):
    """The mirror against a fake transport. It has never been run against the live API here."""

    def setUp(self):
        super().setUp()
        os.environ.update(LINEAR_API_KEY="test-key", LINEAR_TEAM="OPS")
        self.calls, self.remote_state = [], "Todo"
        self.real = core.linear_gql
        core.linear_gql = self.fake

    def tearDown(self):
        core.linear_gql = self.real
        super().tearDown()

    def fake(self, query, variables=None):
        self.calls.append((query, variables))
        if "teams(" in query:
            return {"teams": {"nodes": [{"id": "team-1", "states": {"nodes": [
                {"id": f"s-{n}", "name": n} for n in ("Todo", "In Progress", "Done", "Canceled")]}}]}}
        if "issueCreate" in query:
            return {"issueCreate": {"issue": {"id": "uuid-1", "url": "https://linear.example/OPS-1"}}}
        if "issue(id:" in query:
            return {"i1": {"state": {"name": self.remote_state}}}
        return {"issueUpdate": {"success": True}, "commentCreate": {"success": True}}

    def test_add_and_approve_are_copied_out(self):
        did = core.add_decision(self.db, "product", "Ship it?", "body")
        d = core.get_decision(self.db, did)
        self.assertEqual((d["external_id"], d["external_url"]), ("uuid-1", "https://linear.example/OPS-1"))
        core.move(self.db, did, "approve", "Go.")
        self.assertEqual(sum("issueCreate" in q for q, v in self.calls), 1)
        sent = [v for q, v in self.calls if "issueUpdate" in q]
        self.assertEqual(sent, [{"id": "uuid-1", "s": "s-In Progress"}])
        self.assertTrue(any("commentCreate" in q and v["i"]["body"] == "Go." for q, v in self.calls))

    def test_a_mirror_failure_never_blocks_the_local_write(self):
        def down(query, variables=None):
            raise OSError("network down")
        core.linear_gql = down
        with contextlib.redirect_stderr(io.StringIO()) as err:
            did = core.add_decision(self.db, "product", "Ship it?")
            self.assertEqual(core.move(self.db, did, "approve"), "in_progress")
        self.assertIn("Linear mirror skipped", err.getvalue())

    def test_pull_copies_an_approval_made_in_linear(self):
        did = core.add_decision(self.db, "product", "Ship it?")
        self.remote_state = "In Progress"
        self.assertEqual(core.pull(self.db), [(did, "in_progress")])
        self.assertEqual([d["id"] for d in core.dispatch_ready(self.db)], [did])


if __name__ == "__main__":
    unittest.main()
