"""The console over HTTP, against the seeded demo data."""
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from support import LanesCase, core, load

console = load("console", "console/console.py")
console.core = core      # the same module object the tests configure
console.DEMO = True      # never ask systemd about the host's timers


class Console(LanesCase):
    def setUp(self):
        super().setUp()
        self.db.close()
        core.os.remove(core.db_path())
        self.db = core.seed_demo(self.tmp)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), console.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path, headers=None):
        with urllib.request.urlopen(urllib.request.Request(self.base + path, headers=headers or {})) as r:
            return r.status, r.read().decode(errors="replace"), r.headers

    def post(self, path, headers=None, **form):
        req = urllib.request.Request(self.base + path, data=urllib.parse.urlencode(form).encode(), headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:   # follows the 303 back to the page
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_four_pages_render_from_the_seed(self):
        for path, needle in (("/", "Waiting on your decision"), ("/lanes", "pipeline-followup"),
                             ("/inbox", "need you"), ("/queue", "waiting on you")):
            status, body, _ = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(needle, body, path)
            self.assertNotIn("Traceback", body)

    def test_a_seeded_failed_run_shows_on_today(self):
        _, body, _ = self.get("/")
        self.assertIn("Failed runs, last 7 days (1)", body)
        self.assertIn("<code>pipeline-followup</code> on outreach", body)
        self.assertIn("Lanes past cadence (1)", body)

    def test_approve_makes_dispatch_check_list_it(self):
        self.assertEqual([d["id"] for d in core.dispatch_ready(self.db)], [4])
        status, body = self.post("/act/decision", id="2", action="approve", comment="Go.", back="/queue#D-2")
        self.assertEqual(status, 200)
        self.assertIn("D-2 approved", body)
        self.assertEqual([d["id"] for d in core.dispatch_ready(self.db)], [4, 2])

    def test_a_closed_decision_cannot_be_approved_from_the_page(self):
        _, body = self.post("/act/decision", id="6", action="approve", back="/queue")
        self.assertIn("Not done", body)
        self.assertEqual(core.get_decision(self.db, 6)["state"], "declined")

    def test_mark_read_takes_an_item_off_needs_you(self):
        before = len(core.needs_you(self.db))
        self.post("/act/deliverable", id=str(core.needs_you(self.db)[0]["id"]), status="read", back="/inbox")
        self.assertEqual(len(core.needs_you(self.db)), before - 1)

    def test_a_cross_site_post_is_refused(self):
        status, _ = self.post("/act/decision", headers={"Origin": "http://evil.example"}, id="2", action="approve")
        self.assertEqual(status, 403)
        self.assertEqual(core.get_decision(self.db, 2)["state"], "todo")

    def test_the_redirect_only_goes_back_to_this_console(self):
        import http.client
        for back in ("/x\r\nSet-Cookie: a=1", "/\\evil.example", "//evil.example", "https://evil.example"):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
            conn.request("POST", "/act/deliverable", urllib.parse.urlencode({"id": "1", "status": "read", "back": back}),
                         {"Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            self.assertEqual((r.status, r.getheader("Location"), r.getheader("Set-Cookie")), (303, "/", None), back)
            conn.close()

    def test_the_flash_message_cannot_carry_a_link(self):
        _, body, _ = self.get("/?msg=" + urllib.parse.quote("[click](https://evil.example) and `code` <b>x</b>"))
        self.assertNotIn("<a href=\"https://evil.example", body)
        self.assertIn("<code>code</code>", body)
        self.assertIn("&lt;b&gt;", body)

    def test_a_request_for_another_host_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/", headers={"Host": "evil.example"})
        self.assertEqual(e.exception.code, 403)
        e.exception.close()

    def test_markdown_html_and_pdf_render_in_place(self):
        rows = {core.os.path.splitext(r["path"])[1]: r["id"] for r in self.db.execute("select id, path from deliverables")}
        rows[".md"] = self.db.execute("select id from deliverables where path like '%followups.md'").fetchone()[0]
        self.assertIn("<table>", self.get(f"/d/{rows['.md']}")[1])
        self.assertIn("<iframe class=frame sandbox", self.get(f"/d/{rows['.html']}")[1])
        self.assertIn('type="application/pdf"', self.get(f"/d/{rows['.pdf']}")[1])
        _, _, headers = self.get(f"/raw/{rows['.html']}")
        self.assertEqual(headers["Content-Security-Policy"], "sandbox")    # agent HTML can't script the console
        _, body, headers = self.get(f"/raw/{rows['.pdf']}")
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertTrue(body.startswith("%PDF-1.4"))

    def test_markdown_escapes_html(self):
        out = console.md_html("# Title\n\n<script>alert(1)</script> and **bold** and [x](javascript:alert(1))")
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("<strong>bold</strong>", out)
        self.assertNotIn("<a href", out)      # only http and https links become links


if __name__ == "__main__":
    unittest.main()
