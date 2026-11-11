#!/usr/bin/env python3
"""console.py: a small local console for headless lanes. One file, standard library only.

  python3 console/console.py --demo          seed a throwaway database with made-up data and serve it
  python3 console/console.py [--port 8787]   serve the real one (LANES_DB, LANES_DIR, LANES_LOG_DIR)

Four pages. Today: what needs a human now. Lanes: every lane's last run and a Run now button.
Inbox: everything the lanes made, rendered in place. Queue: decisions waiting on a human;
Approve moves one to in_progress, which is what `lanes dispatch-check` hands a dispatcher lane.

It binds to 127.0.0.1 and has no login. Anyone who can reach the port can approve decisions and
start lanes, so keep it on loopback (or behind something that authenticates) and never on 0.0.0.0.
"""
import argparse
import datetime as dt
import glob
import html
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from urllib.parse import parse_qs, quote, urlsplit

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.dont_write_bytecode = True
_loader = SourceFileLoader("lanes_core", os.path.join(ROOT, "bin", "lanes"))
core = importlib.util.module_from_spec(importlib.util.spec_from_loader("lanes_core", _loader))
_loader.exec_module(core)  # the CLI is the library: one schema, one set of rules

DEMO = False
RUNNER = os.path.join(ROOT, "bin", "lane-run.sh")
UNIT_DIR = os.path.expanduser("~/.config/systemd/user")
TYPES = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".pdf": "application/pdf",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp", ".svg": "image/svg+xml"}
SECTIONS = (("act", "Needs you", True), ("decision", "With its decision: read it when you decide", True),
            ("read", "Worth reading", True), ("fyi", "FYI", False), ("parked", "Parked", False))

CSS = """
:root{--bg:#f4f2ed;--card:#fff;--ink:#1c1a17;--mute:#6b665d;--faint:#9a9488;--line:#e4dfd5;--line2:#eeeae2;
--acc:#2b6a57;--acc-ink:#fff;--acc-soft:#e2efe9;--ok:#2e7d4f;--ok-ink:#fff;--ok-soft:#e1f0e6;--warn:#94600a;
--warn-soft:#f6ebd5;--bad:#b3362f;--bad-soft:#f8e3e1;--chip:#efebe3;
--shadow:0 1px 2px rgba(28,26,23,.05),0 1px 3px rgba(28,26,23,.04);--r:12px;
--mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#131311;--card:#1c1b18;--ink:#ebe7e0;--mute:#a49e93;--faint:#7b766d;
--line:#2f2c27;--line2:#262421;--acc:#86c3ae;--acc-ink:#0e1d17;--acc-soft:#1d2e27;--ok:#6cc08b;--ok-ink:#0d1f13;
--ok-soft:#1b2c21;--warn:#e0a83a;--warn-soft:#30271a;--bad:#e8786f;--bad-soft:#382220;--chip:#272522;--shadow:none}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,
"Noto Sans",sans-serif;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline;text-underline-offset:2px}
code,pre{font-family:var(--mono);font-size:.9em}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:4px}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
.bar{max-width:1320px;margin:0 auto;padding:10px 20px;display:flex;gap:14px;align-items:center}
.bar h1{font-size:15px;font-weight:700;margin:0;white-space:nowrap;letter-spacing:-.01em}
.bar h1 a{color:var(--ink);display:flex;align-items:center;gap:8px}.bar h1 a:hover{text-decoration:none}
.bar h1 i{width:22px;height:22px;border-radius:6px;background:var(--acc);display:inline-block;position:relative}
.bar h1 i:after{content:"";position:absolute;left:5px;right:5px;top:6px;height:2px;background:var(--acc-ink);
box-shadow:0 4px 0 var(--acc-ink),0 8px 0 var(--acc-ink)}
.tabs{display:flex;gap:2px;flex:1;min-width:0;overflow-x:auto}
.tabs a{color:var(--mute);padding:5px 8px;border-radius:8px;font-size:14px;white-space:nowrap;display:flex;
align-items:center;gap:6px}
.tabs a:hover{color:var(--ink);background:var(--chip);text-decoration:none}
.tabs a.on{color:var(--ink);background:var(--card);box-shadow:inset 0 0 0 1px var(--line),var(--shadow);font-weight:600}
.badge{background:var(--acc);color:var(--acc-ink);border-radius:99px;font-size:11px;font-weight:700;padding:0 6px;
line-height:17px;min-width:17px;text-align:center}
main{max-width:1320px;margin:0 auto;padding:20px 20px 56px}
h2{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--mute);margin:28px 0 10px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:16px;align-items:start}
.cols>*{min-width:0}
.panel{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;
box-shadow:var(--shadow);min-width:0;overflow-wrap:break-word;overflow-x:auto;margin:0 0 16px}
.cols>.panel{margin:0}.panel h2{margin:0 0 10px}.panel.wide{grid-column:1/-1}
.panel>ul{list-style:none;margin:0;padding:0}.panel>ul>li{padding:8px 0;border-top:1px solid var(--line2)}
.panel>ul>li:first-child{border-top:0;padding-top:2px}.panel>ul>li:last-child{padding-bottom:2px}
.panel p:last-child{margin-bottom:0}.panel>h2+p{margin-top:0}
.done{color:var(--mute)}.empty{color:var(--mute);margin:0}.src{font-size:12.5px;color:var(--mute)}
.due{color:var(--warn)}.x{color:var(--mute)}
.flash{background:var(--acc-soft);border:1px solid color-mix(in srgb,var(--acc) 35%,var(--line));border-radius:10px;
padding:9px 14px;margin:0 0 16px}
.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:0 8px;font-size:12px;line-height:20px;
color:var(--mute);white-space:nowrap;vertical-align:1px}
.chip.ok,.chip.acted,.chip.done,.chip.ready{color:var(--ok);background:var(--ok-soft)}
.chip.warn,.chip.locked,.chip.in_progress{color:var(--warn);background:var(--warn-soft)}
.chip.error,.chip.timeout,.chip.declined{color:var(--bad);background:var(--bad-soft)}
.chip.unread,.chip.demo{color:var(--acc);background:var(--acc-soft)}.chip.superseded{text-decoration:line-through}
button{font:inherit;font-size:14px;font-weight:500;line-height:1.3;border-radius:8px;border:1px solid var(--line);
padding:7px 14px;cursor:pointer;background:var(--card);color:var(--ink);white-space:nowrap}
button:hover{border-color:var(--faint)}
button.approve{background:var(--ok);color:var(--ok-ink);border-color:transparent}button.approve:hover{filter:brightness(1.07)}
button.reject{color:var(--bad)}button.small{padding:3px 10px;font-size:13px}
.btns{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}form.inline{display:inline}
textarea{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:7px 10px;width:100%;min-height:44px;margin-top:12px;resize:vertical}
textarea:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-soft)}
details summary{cursor:pointer;color:var(--mute)}details summary:hover{color:var(--ink)}
details.run{display:inline-block}details.run summary{list-style:none;font-size:13px;border:1px solid var(--line);
border-radius:8px;padding:2px 10px;color:var(--ink)}details.run summary::-webkit-details-marker{display:none}
details.run[open] summary{display:none}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font-size:12px;font-weight:600;color:var(--mute);text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);
white-space:nowrap}
td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
tr:last-child>td{border-bottom:0}th:first-child,td:first-child{padding-left:0}th:last-child,td:last-child{padding-right:0}
td.nw{white-space:nowrap}td.sum{color:var(--mute);font-size:13px}
.ihead{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 14px}
.ihead .big{font-size:22px;font-weight:700;letter-spacing:-.01em}
.tbox{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:2px 16px}
.tbox.act{border-color:color-mix(in srgb,var(--acc) 45%,var(--line));box-shadow:0 0 0 3px var(--acc-soft)}
table.inbox td{padding:11px 10px}table.inbox td.act{text-align:right;white-space:nowrap;width:1%}
.inbox a.t{color:var(--ink);font-weight:600}.inbox tr:not(.unread) a.t{color:var(--mute);font-weight:500}
.inbox tr.unread a.t:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;
background:var(--acc);margin:0 8px 2px 0;vertical-align:middle}
.imeta{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center;font-size:12.5px;color:var(--mute);margin-top:4px}
.imeta a{font-weight:600}.path{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-top:2px;
overflow-wrap:anywhere}
.doc{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
padding:28px 32px;max-width:860px;line-height:1.65;overflow-wrap:break-word}
.doc h1{font-size:24px;line-height:1.25;margin:0 0 14px}.doc h2{font-size:18px;text-transform:none;letter-spacing:0;
color:var(--ink);margin:26px 0 8px}.doc h3,.doc h4{font-size:15.5px;margin:20px 0 6px}
.doc pre,.md pre{background:var(--chip);padding:12px 14px;border-radius:8px;overflow:auto;font-size:13px;white-space:pre-wrap}
.doc code,.md code{font-size:13px;background:var(--chip);padding:1px 5px;border-radius:4px}
.doc pre code,.md pre code{background:none;padding:0}
.doc blockquote{border-left:3px solid var(--acc-soft);margin:0;padding:0 0 0 14px;color:var(--mute)}
.doc table{margin:10px 0}.doc hr{border:0;border-top:1px solid var(--line);margin:22px 0}.doc img{max-width:100%}
.md p{margin:6px 0}.md ul,.md ol{margin:6px 0;padding-left:22px}
.frame{width:100%;height:80vh;border:1px solid var(--line);border-radius:var(--r);background:#fff}
.dhead{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:0 0 14px}
.dhead h1{font-size:21px;line-height:1.3;margin:0;letter-spacing:-.01em}
.card h3{font-size:16px;margin:0 0 6px;font-weight:650}.card .who{font-size:12.5px;color:var(--mute);margin-top:12px}
.card .cm{border-top:1px solid var(--line2);margin-top:10px;padding-top:2px}
@media (max-width:760px){header{position:static}.bar{flex-wrap:wrap;padding:10px 16px}main{padding:14px 16px 40px}
.panel{padding:14px}.doc{padding:18px 16px}.panel table,.doc table{display:block;overflow-x:auto}.path{display:none}}
"""
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' "
           "height='32' rx='8' fill='%232b6a57'/%3E%3Cpath d='M8 11h16M8 16h16M8 21h16' stroke='white' "
           "stroke-width='3'/%3E%3C/svg%3E")


# ---------------------------------------------------------------- small helpers
def esc(s):
    return html.escape(str("" if s is None else s))


def chip(text, cls=""):
    return f'<span class="chip {esc(cls)}">{esc(text)}</span>'


def rel_date(d):
    """Today, Yesterday, a weekday within the week, else 'Oct 28'."""
    try:
        day = dt.date.fromisoformat(str(d)[:10])
    except ValueError:
        return str(d or "")
    n = (dt.date.today() - day).days
    if n in (0, 1):
        return ("Today", "Yesterday")[n]
    return day.strftime("%A") if 1 < n < 7 else day.strftime("%b %-d")


def when(ts):
    return f"{rel_date(ts)} {str(ts)[11:16]}" if ts else ""


def dur(secs):
    return f"{int(secs) // 60}m{int(secs) % 60:02d}s" if secs else ""


def panel(title, body, cls=""):
    return f'<section class="panel {cls}"><h2>{esc(title)}</h2>{body}</section>'


def ul(items, empty):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else f"<p class=empty>{esc(empty)}</p>"


def post(action, fields, label, back, cls="small"):
    """A one-button form. Every state change is a POST that redirects back to the page."""
    hidden = "".join(f'<input type=hidden name="{esc(k)}" value="{esc(v)}">' for k, v in {**fields, "back": back}.items())
    return f'<form class=inline method=post action="{action}">{hidden}<button class="{cls}">{esc(label)}</button></form>'


# ---------------------------------------------------------------- markdown, enough for agent output
def md_inline(t):
    t, codes = esc(t), []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", stash, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noreferrer" target="_blank">\1</a>', t)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", t)


def md_html(text):
    """Headings, paragraphs, lists, tables, fenced code, quotes, rules. Everything is escaped
    first; raw HTML in a file an agent wrote is shown as text, never run."""
    out, para, lines, i = [], [], text.splitlines(), 0
    item = re.compile(r"\s*([-*]|\d+[.)])\s+(.*)")

    def flush():
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para.clear()

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append("<pre><code>" + esc("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif m := re.match(r"(#{1,4})\s+(.*)", s):
            flush()
            out.append(f"<h{len(m.group(1))}>{md_inline(m.group(2))}</h{len(m.group(1))}>")
            i += 1
        elif re.fullmatch(r"-{3,}|\*{3,}", s):
            flush()
            out.append("<hr>")
            i += 1
        elif s.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?[\s:|-]*-[\s:|-]*\|?", lines[i + 1].strip()):
            flush()
            j, rows = i + 2, []
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            out.append("<table><tr>" + "".join(f"<th>{md_inline(c)}</th>" for c in cells(s)) + "</tr>" + "".join(
                "<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
            i = j
        elif m := item.match(lines[i]):
            flush()
            tag, items = ("ul" if m.group(1) in "-*" else "ol"), []
            while i < len(lines):
                if m2 := item.match(lines[i]):
                    items.append(m2.group(2))
                elif lines[i].startswith(("  ", "\t")) and lines[i].strip():
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            box = {"[ ] ": "&#9744; ", "[x] ": "&#9745; "}
            out.append(f"<{tag}>" + "".join(
                f"<li>{box.get(t[:4], '')}{md_inline(t[4:] if t[:4] in box else t)}</li>" for t in items) + f"</{tag}>")
        elif s.startswith(">"):
            flush()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote><p>" + md_inline(" ".join(quote_lines)) + "</p></blockquote>")
        else:
            if s:
                para.append(s)
            else:
                flush()
            i += 1
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- page shell
def page(db, title, tab, body, msg=""):
    badges = {"inbox": len(core.needs_you(db)),
              "queue": db.execute("select count(*) from decisions where state = 'todo'").fetchone()[0]}
    tabs = "".join(f'<a href="{h}" class="{"on" if tab == k else ""}">{t}'
                   + (f"<span class=badge>{badges[k]}</span>" if badges.get(k) else "") + "</a>"
                   for k, h, t in (("today", "/", "Today"), ("lanes", "/lanes", "Lanes"),
                                   ("inbox", "/inbox", "Inbox"), ("queue", "/queue", "Queue")))
    demo = chip("demo data, all made up", "demo") if DEMO else ""
    # the message arrives in the URL: escape it, and allow nothing but `code` spans
    flash = "<p class=flash>" + re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(msg)) + "</p>" if msg else ""
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f'<link rel=icon href="{FAVICON}"><style>{CSS}</style></head><body><header><div class=bar>'
            f'<h1><a href="/"><i></i><span>Lanes console</span></a></h1><nav class=tabs>{tabs}</nav>{demo}'
            f"</div></header><main>{flash}{body}</main></body></html>")


# ---------------------------------------------------------------- Today
def decision_li(d):
    return (f'{chip(d["label"])} <a href="/queue#D-{d["id"]}">D-{d["id"]}</a> {esc(d["title"])} '
            f'<span class=src>{esc(rel_date(d["created_at"]))}</span>')


def today_page(db):
    cfg = core.config()
    todo = db.execute("select * from decisions where state = 'todo' order by id").fetchall()
    need = core.needs_you(db)
    failed = core.open_failures(db)
    late = core.past_cadence(db, cfg)
    ready = core.dispatch_ready(db)
    other = [(sev, line) for sev, line in core.lint(db) if not line.startswith("lane ")]
    body = (f'<p class=done>{dt.date.today():%A %B %-d}</p><div class=cols>'
            + panel(f"Waiting on your decision ({len(todo)})", ul([decision_li(d) for d in todo], "No decision is waiting."))
            + panel(f"Inbox: needs you ({len(need)})", ul(
                [f'{chip(r["lane"])} <a href="/d/{r["id"]}">{esc(r["title"])}</a> <span class=src>{esc(rel_date(r["date"]))}</span>'
                 for r in need], "Nothing unread needs you."))
            + panel(f"Failed runs, last 7 days ({len(failed)})", ul(
                [f'{chip(r["status"], r["status"])} <code>{esc(r["lane"])}</code> on {esc(r["seat"])}, {esc(when(r["started"]))} '
                 f'<a href="/log/{r["id"]}">log</a>' for r in failed], "Every lane's last run ended ok."))
            + panel(f"Lanes past cadence ({len(late)})", ul(
                [f'{chip("late", "warn")} <code>{esc(lane)}</code> last ok run '
                 f'{esc(rel_date(last) if last else "never")}; it should run every {days} days' for lane, days, last in late],
                "Every scheduled lane ran inside its cadence."))
            + panel(f"Approved, waiting on the dispatcher ({len(ready)})", ul(
                [decision_li(d) for d in ready], "Nothing approved is waiting.")
                + "<p class=src>Same list as <code>lanes dispatch-check</code>. With nothing here, the dispatcher's "
                  "timer fires and wakes no seat.</p>")
            + panel("Hygiene", ul([f'{chip(sev, "warn" if sev == "warn" else "")} {esc(line)}' for sev, line in other],
                                  "Clean.") + "<p class=src>From <code>lanes lint</code>; the nightly run files warnings "
                                              "in the Inbox.</p>")
            + "</div>")
    return "Today", "today", body


# ---------------------------------------------------------------- Lanes
def next_timers():
    """{lane: 'Mon 11-16 06:00'} from the systemd user timers named lane-<lane>.timer, if any."""
    if DEMO or not shutil.which("systemctl"):
        return {}
    try:
        out = subprocess.run(["systemctl", "--user", "list-timers", "lane-*", "--all", "-o", "json"],
                             capture_output=True, text=True, timeout=4).stdout
        return {t["activates"][len("lane-"):-len(".service")]: dt.datetime.fromtimestamp(t["next"] / 1e6).strftime("%a %m-%d %H:%M")
                for t in json.loads(out or "[]") if t.get("next") and str(t.get("activates", "")).startswith("lane-")}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return {}


def lane_names(db, cfg):
    names = set(cfg["lanes"]) | {r[0] for r in db.execute("select distinct lane from lane_runs")}
    names |= {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(core.lanes_dir(), "*.md"))}
    return sorted(names - {"README"})


def lanes_page(db):
    cfg, timers = core.config(), next_timers()
    late = {lane for lane, _days, _last in core.past_cadence(db, cfg)}
    rows = []
    for lane in lane_names(db, cfg):
        spec = cfg["lanes"].get(lane, {})
        r = db.execute("select * from lane_runs where lane = ? order by started desc limit 1", (lane,)).fetchone()
        n = db.execute("select count(*) from lane_runs where lane = ?", (lane,)).fetchone()[0]
        nxt = timers.get(lane) or spec.get("schedule") or (f'every {spec["cadence_days"]} days' if spec.get("cadence_days") else "by hand")
        can_run = spec.get("seat") and os.path.isfile(os.path.join(core.lanes_dir(), lane + ".md"))
        run = (f'<details class=run><summary>Run now</summary>{post("/act/run", {"lane": lane}, "Start " + lane, "/lanes")}</details>'
               if can_run else "<span class=x>no prompt</span>")
        last = status = took = log = ""
        if r:
            last, status = esc(when(r["started"])), chip(r["status"], r["status"])
            took = esc(dur(r["duration_s"])) + (f' · {r["turns"]} turns' if r["turns"] else "")
            log = f'<a href="/log/{r["id"]}">log</a>' if r["log"] else ""
        rows.append(
            f'<tr><td class=nw><code>{esc(lane)}</code></td><td>{esc(spec.get("seat") or (r["seat"] if r else ""))}</td>'
            f'<td class=nw>{last or "<span class=x>never</span>"}{" " + chip("past cadence", "warn") if lane in late else ""}</td>'
            f'<td>{status}</td><td class=nw>{took}</td><td>{n}</td><td>{esc(nxt)}</td><td>{log}</td>'
            f'<td class=nw>{run}</td></tr>')
    table = ("<table><tr><th>Lane</th><th>Seat</th><th>Last run</th><th>Status</th><th>Took</th><th>Runs</th>"
             "<th>Next</th><th></th><th></th></tr>" + "".join(rows) + "</table>") if rows else \
        "<p class=empty>No lanes yet. Add a prompt to the lanes folder and a [lanes.name] block to lanes.toml.</p>"
    seats = ul([f'<code>{esc(seat)}</code> {minutes} headless minutes in 7 days'
                + (f' of a soft budget of {budget} {chip("over", "warn") if minutes > budget else ""}' if budget else "")
                for seat, minutes, budget in core.seat_minutes(db, cfg)], "No runs in the last 7 days.")
    recent = "".join(
        f'<tr><td class=nw>{esc(when(r["started"]))}</td><td class=nw><code>{esc(r["lane"])}</code></td><td>{esc(r["seat"])}</td>'
        f'<td>{chip(r["status"], r["status"])}</td><td class=nw>{esc(dur(r["duration_s"]))}</td>'
        f'<td class=sum>{esc((r["summary"] or "")[:160])}</td><td><a href="/log/{r["id"]}">log</a></td></tr>'
        for r in db.execute("select * from lane_runs order by started desc limit 15"))
    body = (panel("Lanes", table + "<p class=src>One run per seat at a time: Run now waits its turn behind the seat's "
                                   "lock, and a run that does not end ok lands in the Inbox.</p>")
            + '<div class=cols>' + panel("Seats", seats)
            + panel("Recent runs", f"<table>{recent}</table>" if recent else "<p class=empty>No runs yet.</p>", "wide") + "</div>")
    return "Lanes", "lanes", body


def start_lane(lane):
    """Start a lane detached from the console, through the same runner and the same seat lock a
    timer uses. An installed unit is started as is; otherwise a transient systemd-run unit; with
    no systemd (or in the demo) a plain detached process."""
    spec = core.config()["lanes"].get(lane)
    if not spec or not spec.get("seat") or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", lane):
        raise ValueError(f"no lane {lane} with a seat in lanes.toml")
    env = {k: v for k, v in os.environ.items() if k.startswith(("LANES_", "LANE_"))}  # the console's own settings
    unit = f"lane-{lane}.service"
    if DEMO or not shutil.which("systemd-run"):
        if DEMO:  # no Claude seat in the demo: a stand-in sleeps a few seconds and prints an envelope
            env.update(LANE_CLAUDE_BIN=os.path.join(ROOT, "tests", "fake-claude"), LANE_SKIP_LOGIN_CHECK="1",
                       FAKE_CLAUDE_SLEEP="3", LANE_LOCK_WAIT="60")
        subprocess.Popen([RUNNER, spec["seat"], lane], env={**os.environ, **env}, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif os.path.exists(os.path.join(UNIT_DIR, unit)):
        subprocess.run(["systemctl", "--user", "start", "--no-block", unit], check=True, capture_output=True, timeout=5)
    else:
        name = f"lane-{lane}-console-{dt.datetime.now():%Y%m%d-%H%M%S}"
        subprocess.run(["systemd-run", "--user", f"--unit={name}", "--collect", "--property=RuntimeMaxSec=5700",
                        f"--property=OnFailure=lane-failed@{unit}.service", *[f"--setenv={k}={v}" for k, v in env.items()],
                        RUNNER, spec["seat"], lane], check=True, capture_output=True, timeout=10)
    return (f"Started `{lane}` on the {spec['seat']} seat" + (" (demo: a stand-in runs for 3 seconds)" if DEMO else "")
            + ". If the seat is busy it waits its turn. Reload to see the run.")


# ---------------------------------------------------------------- Inbox
def inbox_row(r, back):
    target = f'<a class=t href="/d/{r["id"]}">{esc(r["title"])}</a>'
    dec = f'<a href="/queue#{esc(r["decision"])}">{esc(r["decision"])}</a>' if r["decision"] else ""
    st = chip(r["status"], r["status"]) if r["status"] != "unread" else ""
    btn = post("/act/deliverable", {"id": r["id"], "status": "read" if r["status"] == "unread" else "unread"},
               "Mark read" if r["status"] == "unread" else "Unread", back)
    return (f'<tr class="{esc(r["status"])}"><td>{target}<div class=imeta>{esc(rel_date(r["date"]))} {chip(r["lane"])} '
            f'{chip(r["kind"])} {dec} {st}</div><div class=path>{esc(r["path"] or r["url"])}</div></td>'
            f'<td class=act>{btn}</td></tr>')


def inbox_page(db):
    rows = db.execute("select * from deliverables order by date desc, id desc").fetchall()
    unread = [r for r in rows if r["status"] == "unread"]
    by = {}
    for r in unread:
        by.setdefault(core.section(r), []).append(r)
    body = (f'<div class=ihead><span class=big>{len(by.get("act", []))} need you</span><span class=src>{len(unread)} unread in '
            f'all. The nightly sweep clears rows whose decision closed, expired items, and FYI after {core.FYI_DAYS} days.</span></div>')
    for key, title, is_open in SECTIONS:
        items = by.get(key, [])
        if not items and key != "act":
            continue
        inner = (f'<div class="tbox {"act" if key == "act" else ""}"><table class=inbox>'
                 + "".join(inbox_row(r, "/inbox") for r in items) + "</table></div>") if items else \
            "<p class=empty>Nothing needs you.</p>"
        body += (f"<h2>{esc(title)} ({len(items)})</h2>{inner}" if is_open else
                 f"<details><summary><h2 style='display:inline-block'>{esc(title)} ({len(items)})</h2></summary>{inner}</details>")
    seen = [r for r in rows if r["status"] != "unread"][:30]
    if seen:
        body += (f"<details><summary><h2 style='display:inline-block'>Read ({len(seen)})</h2></summary><div class=tbox>"
                 f"<table class=inbox>{''.join(inbox_row(r, '/inbox') for r in seen)}</table></div></details>")
    return "Inbox", "inbox", body


def render_file(r):
    """A deliverable shown in place. HTML goes in a sandboxed frame, a PDF in an embed, markdown
    through the renderer above; everything else is shown as text."""
    if r["url"]:
        return f'<div class=doc><p>This item is a link: <a href="{esc(r["url"])}" rel="noreferrer" target="_blank">{esc(r["url"])}</a></p></div>'
    p = os.path.expanduser(r["path"])
    if not os.path.isfile(p):
        return f'<div class=doc><p>{chip("file not found", "error")} <code>{esc(r["path"])}</code></p></div>'
    ext = os.path.splitext(p)[1].lower()
    if ext in (".html", ".htm"):
        return f'<iframe class=frame sandbox src="/raw/{r["id"]}" title="{esc(r["title"])}"></iframe>'
    if ext == ".pdf":
        return f'<embed class=frame src="/raw/{r["id"]}" type="application/pdf">'
    if ext in TYPES:
        return f'<div class=doc><img src="/raw/{r["id"]}" alt="{esc(r["title"])}"></div>'
    with open(p, errors="replace") as f:
        text = f.read(400_000)
    return f'<div class=doc>{md_html(text) if ext in (".md", ".markdown") else "<pre>" + esc(text) + "</pre>"}</div>'


def deliverable_page(db, rid):
    r = db.execute("select * from deliverables where id = ?", (rid,)).fetchone()
    if not r:
        return None
    back = f"/d/{rid}"
    btns = "".join(post("/act/deliverable", {"id": rid, "status": s}, label, back, "")
                   for s, label in (("read", "Mark read"), ("acted", "Done with it"), ("unread", "Unread")) if s != r["status"])
    dec = f'<a href="/queue#{esc(r["decision"])}">{esc(r["decision"])}</a>' if r["decision"] else ""
    body = (f'<div class=dhead><h1>{esc(r["title"])}</h1></div><div class=imeta style="margin:0 0 12px">{esc(rel_date(r["date"]))} '
            f'{chip(r["lane"])} {chip(r["kind"])} {chip("needs: " + r["needs"])} {chip(r["status"], r["status"])} {dec} '
            f'<span class=path>{esc(r["path"] or r["url"])}</span></div><div class=btns style="margin:0 0 16px">{btns}</div>'
            + render_file(r))
    return r["title"], "inbox", body


def log_page(db, rid):
    r = db.execute("select * from lane_runs where id = ?", (rid,)).fetchone()
    if not r:
        return None
    p = os.path.realpath(os.path.expanduser(r["log"] or ""))
    inside = p.startswith(os.path.realpath(core.log_dir()) + os.sep)  # only ever read a file under the log folder
    text = open(p, errors="replace").read(400_000) if inside and os.path.isfile(p) else "(no log on disk for this run)"
    body = (f'<div class=dhead><h1><code>{esc(r["lane"])}</code> on {esc(r["seat"])}</h1>{chip(r["status"], r["status"])}</div>'
            f'<div class=imeta style="margin:0 0 12px">{esc(when(r["started"]))} · {esc(dur(r["duration_s"]) or "0s")} · '
            f'{esc(r["turns"] or 0)} turns · {esc(r["input_tokens"] or 0)} tokens in, {esc(r["output_tokens"] or 0)} out '
            f'<span class=path>{esc(r["log"])}</span></div><div class=doc><pre>{esc(text)}</pre></div>')
    return f"{r['lane']} log", "lanes", body


# ---------------------------------------------------------------- Queue
def decision_card(db, d, ready):
    ident = f"D-{d['id']}"
    files = db.execute("select * from deliverables where decision = ? order by id", (ident,)).fetchall()
    comments = db.execute("select * from decision_comments where decision_id = ? order by id", (d["id"],)).fetchall()
    note = ""
    if d["state"] == "in_progress":
        note = (chip("ready for the dispatcher", "ready") if d["id"] in ready else
                chip("answered or being worked; comment or approve again to send it back", "warn"))
    out = (f'<section class="panel card" id="{ident}"><div class=imeta>{chip(d["label"])} <strong>{ident}</strong> '
           f'{chip(d["state"].replace("_", " "), d["state"])} {note} <span>filed {esc(rel_date(d["created_at"]))}</span></div>'
           f'<h3>{esc(d["title"])}</h3><div class=md>{md_html(d["body"])}</div>')
    if files:
        out += "<p class=src>In the Inbox: " + " · ".join(f'<a href="/d/{f["id"]}">{esc(f["title"])}</a>' for f in files) + "</p>"
    for c in comments:
        out += (f'<div class=cm><div class=who>{chip("agent" if c["author"] == "agent" else "you")} '
                f'{esc(when(c["created_at"]))}</div><div class=md>{md_html(c["body"])}</div></div>')
    if d["state"] in ("todo", "in_progress"):
        first = ("approve", "Approve", "approve") if d["state"] == "todo" else ("approve", "Approve again", "")
        buttons = [first, ("decline", "Decline", "reject"), ("comment", "Comment only", "")]
        if d["state"] == "in_progress":
            buttons.insert(1, ("done", "Mark done", ""))
        out += (f'<form method=post action="/act/decision"><input type=hidden name=id value="{d["id"]}">'
                f'<input type=hidden name=back value="/queue#{ident}">'
                f'<textarea name=comment placeholder="Comment (optional). Picks and conditions go here." aria-label="Comment"></textarea>'
                f'<div class=btns>' + "".join(f'<button name=action value="{a}" class="{c}">{label}</button>'
                                              for a, label, c in buttons) + "</div></form>")
    return out + "</section>"


def queue_page(db):
    ready = {d["id"] for d in core.dispatch_ready(db)}
    rows = db.execute("select * from decisions order by id").fetchall()
    todo = [d for d in rows if d["state"] == "todo"]
    going = [d for d in rows if d["state"] == "in_progress"]
    closed = [d for d in rows if d["state"] in ("done", "declined")][-10:]
    body = (f'<div class=ihead><span class=big>{len(todo)} waiting on you</span><span class=src>An agent files a decision only '
            f'when it needs a human. Approve moves it to in progress; <code>lanes dispatch-check</code> hands those to the '
            f'dispatcher lane.</span></div>')
    body += "".join(decision_card(db, d, ready) for d in todo) or "<p class=empty>No decision is waiting.</p>"
    body += f"<h2>Approved ({len(going)})</h2>" + ("".join(decision_card(db, d, ready) for d in going)
                                                   or "<p class=empty>Nothing is in progress.</p>")
    if closed:
        body += (f"<details><summary><h2 style='display:inline-block'>Closed ({len(closed)})</h2></summary>"
                 + "".join(decision_card(db, d, ready) for d in reversed(closed)) + "</details>")
    return "Queue", "queue", body


# ---------------------------------------------------------------- actions (POST)
def act_deliverable(db, f):
    if f.get("status") not in ("read", "unread", "acted"):
        raise ValueError("status is read, unread or acted")
    core.set_status(db, int(f["id"]), f["status"])
    return ""


def act_decision(db, f):
    action, text = f.get("action", ""), f.get("comment", "").strip()
    if action == "comment":
        if not text:
            raise ValueError("Write the comment first.")
        core.add_comment(db, f["id"], text)
        return "Comment added."
    if action not in core.MOVES:
        raise ValueError("unknown action")
    new = core.move(db, f["id"], action, text)
    ident = f"D-{core.ident(f['id'])}"
    if action == "approve":
        return f"{ident} approved. `lanes dispatch-check` lists it now, and the next dispatcher run works it."
    return f"{ident} is {new.replace('_', ' ')}."


def act_run(db, f):
    return start_lane(f.get("lane", ""))


PAGES = {"/": today_page, "/lanes": lanes_page, "/inbox": inbox_page, "/queue": queue_page}
ITEM_PAGES = {"d": deliverable_page, "log": log_page}
ACTIONS = {"/act/deliverable": act_deliverable, "/act/decision": act_decision, "/act/run": act_run}


class Handler(BaseHTTPRequestHandler):
    server_version = "lanes-console"

    def log_message(self, *args):  # the terminal stays quiet; the pages are the log
        pass

    def reply(self, code, body, ctype="text/html; charset=utf-8", headers=()):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        for k, v in (("Content-Type", ctype), ("Content-Length", str(len(data))), ("X-Content-Type-Options", "nosniff"),
                     ("Referrer-Policy", "no-referrer"), *headers):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def local(self):
        """Only answer requests addressed to loopback, so a hostile page can't reach the console
        through a DNS name that resolves to 127.0.0.1."""
        return self.headers.get("Host", "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost", "[::1]")

    def do_GET(self):
        if not self.local():
            return self.reply(403, "forbidden", "text/plain")
        url = urlsplit(self.path)
        msg = parse_qs(url.query).get("msg", [""])[0]
        db = core.connect()
        try:
            m = re.fullmatch(r"/(d|log|raw)/(\d+)", url.path)
            if url.path in PAGES:
                out = PAGES[url.path](db)
            elif m and m.group(1) == "raw":
                return self.raw(db, int(m.group(2)))
            elif m:
                out = ITEM_PAGES[m.group(1)](db, int(m.group(2)))
            else:
                out = None
            if out is None:
                return self.reply(404, page(db, "Not found", "", "<p class=empty>Nothing here.</p>"))
            self.reply(200, page(db, out[0], out[1], out[2], msg))
        except Exception as e:  # a local tool: show the error instead of a blank page
            self.reply(500, page(db, "Error", "", f"<div class=doc><pre>{esc(type(e).__name__)}: {esc(e)}</pre></div>"))
        finally:
            db.close()

    def raw(self, db, rid):
        """The bytes of a registered deliverable, for the frame, embed and img tags. Only files a
        row points at are served, and HTML is served with a sandbox policy so it cannot script
        the console."""
        r = db.execute("select path from deliverables where id = ?", (rid,)).fetchone()
        p = os.path.expanduser(r["path"]) if r and r["path"] else ""
        if not os.path.isfile(p):
            return self.reply(404, "not found", "text/plain")
        with open(p, "rb") as f:
            data = f.read()
        ctype = TYPES.get(os.path.splitext(p)[1].lower(), "text/plain; charset=utf-8")
        self.reply(200, data, ctype, (("Content-Security-Policy", "sandbox"),))

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.local() or (origin and origin != f"http://{self.headers.get('Host')}"):
            return self.reply(403, "forbidden: cross-site request", "text/plain")
        length = self.headers.get("Content-Length") or "0"
        n = int(length) if length.isdigit() else -1
        action = ACTIONS.get(urlsplit(self.path).path)
        if not action or not 0 <= n <= 65536:
            return self.reply(404 if not action else 400, "not found" if not action else "bad request", "text/plain")
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
        db = core.connect()
        try:
            msg = action(db, form)
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
            msg = f"Not done: {e}"
        finally:
            db.close()
        back = form.get("back", "/")
        if not re.fullmatch(r"/[A-Za-z0-9/_-]*(#[A-Za-z0-9_-]*)?", back) or back.startswith("//"):
            back = "/"  # only this console's own paths: no other site, no header injection
        path, _, frag = back.partition("#")
        self.send_response(303)
        self.send_header("Location", path + (f"?msg={quote(msg)}" if msg else "") + (f"#{frag}" if frag else ""))
        self.end_headers()


def main():
    global DEMO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="seed a throwaway database with made-up data and serve it")
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    try:  # take the port before seeding anything, so a busy port leaves nothing behind
        server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        sys.exit(f"console: can't listen on 127.0.0.1:{a.port} ({e.strerror}). Try --port {a.port + 1}.")
    tmp = None
    if a.demo:
        DEMO = True
        tmp = tempfile.mkdtemp(prefix="headless-lanes-demo-")
        os.environ.update(LANES_DB=os.path.join(tmp, "lanes.db"), LANES_DIR=os.path.join(tmp, "lanes"),
                          LANES_LOG_DIR=os.path.join(tmp, "logs"))
        core.seed_demo(tmp).close()
        for lane in core.config()["lanes"]:
            with open(os.path.join(core.lanes_dir(), lane + ".md"), "w") as f:
                f.write(f"Demo prompt for {lane}. The real examples are in examples/.\n")
    else:
        core.connect().close()
    print(f"Lanes console: http://127.0.0.1:{a.port}" + ("  (demo data, deleted on exit)" if DEMO else f"  ({core.db_path()})"),
          flush=True)
    if DEMO:
        print(f"Same database from another terminal:\n  export LANES_DB={os.environ['LANES_DB']} LANES_DIR={os.environ['LANES_DIR']}\n"
              f"  bin/lanes dispatch-check", flush=True)
    def stop(*_):  # systemd and `kill` send SIGTERM; treat it like Ctrl-C so the demo cleans up
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
