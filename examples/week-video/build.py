#!/usr/bin/env python3
"""build.py: turn one week export into a video composition (build/index.html beside this file).

  python3 build.py demo-week.json
  python3 build.py week.json --title "What my agents did last week" --out ./my-week
  python3 build.py week.json --width 1080 --height 1920        # a vertical cut

The composition is plain HTML with a paused GSAP timeline, 30 seconds at 30 fps. Every block,
tick and label is written into the file here, so the page fetches no data and every frame is a
function of time alone. Python standard library only.
"""
import argparse
import datetime as dt
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
FPS = 30
LENGTH = 30.0          # seconds of video
SWEEP = (2.5, 24.0)    # the playhead crosses the window between these two moments
CLOSE = 24.6           # the closing frame comes up here
MIN_BLOCK = 6          # px at 1080p: a run shorter than this is drawn this wide, so it can be seen
KIND_COLOR = {"report": "#5b8def", "pipeline": "#3fb8a9", "render": "#b38cf0",
              "dispatcher": "#e8b04b", "build": "#9db86a"}
FAIL = "#ef5350"
LOCK = "#d6dbe3"
INK, DIM, FAINT, BG = "#eef1f5", "#9aa3af", "#3a414c", "#12151a"


def fmt_day(d):
    return f"{d:%a} {d.day} {d:%b}"


def fmt_range(start, end):
    last = end - dt.timedelta(seconds=1)
    if start.year == last.year:
        return f"{fmt_day(start)} to {fmt_day(last)} {last.year}"
    return f"{fmt_day(start)} {start.year} to {fmt_day(last)} {last.year}"


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def hours_text(seconds):
    return f"{seconds / 3600:.1f}"


def subset_line(ex):
    """What the picture leaves out, from the export's own numbers. Always says how many lanes are
    shown; says the left-out runs whenever there are any, because then a gap is not idle time."""
    lanes = plural(ex["lanes_shown"], "lane") + " shown"
    n = ex["runs_left_out"]
    if n:
        return f"{lanes}. {plural(n, 'run')} from lanes not shown are left out, so a gap is not idle time."
    return f"{lanes}. No run in the window is left out."


def build(ex, title, width, height):
    s = height / 1080                       # every size below is for 1080p and scales with the frame
    px = lambda v: round(v * s, 1)          # noqa: E731
    start = dt.datetime.fromisoformat(ex["window"]["start"])
    end = dt.datetime.fromisoformat(ex["window"]["end"])
    span = ex["window"]["seconds"]
    seats = ex["seats"] or ["seat 1"]
    tot = ex["totals"]

    # layout (1080p numbers, scaled)
    left, right = px(190), width - px(70)
    top, bottom = px(250), height - px(300)
    plot_w = right - left
    gap = px(18)
    lane_h = min(px(240), (bottom - top - gap * (len(seats) - 1)) / len(seats))
    bar_h = lane_h * 0.42
    x_at = lambda sec: left + plot_w * sec / span   # noqa: E731
    t_at = lambda sec: SWEEP[0] + (SWEEP[1] - SWEEP[0]) * sec / span   # noqa: E731
    lane_y = {seat: top + i * (lane_h + gap) for i, seat in enumerate(seats)}
    plot_bottom = top + len(seats) * lane_h + (len(seats) - 1) * gap

    el, tw = [], []   # markup, tweens

    # day bands, day labels and hour ticks
    day = dt.datetime.combine(start.date(), dt.time())
    k = 0
    while day < end:
        a, b = max(day, start), min(day + dt.timedelta(days=1), end)
        xa, xb = x_at((a - start).total_seconds()), x_at((b - start).total_seconds())
        if k % 2 == 0:
            el.append(f'<div class="band" style="left:{xa:.1f}px;top:{top:.1f}px;width:{xb - xa:.1f}px;'
                      f'height:{plot_bottom - top:.1f}px"></div>')
        if day >= start:
            el.append(f'<div class="dayline" style="left:{xa:.1f}px;top:{top:.1f}px;height:{plot_bottom - top + px(86):.1f}px"></div>')
        if xb - xa > px(90):
            el.append(f'<div class="daylabel" style="left:{xa + px(10):.1f}px;top:{plot_bottom + px(46):.1f}px">'
                      f'{html.escape(f"{a:%a} {a.day}")}</div>')
        for h in (6, 12, 18):
            t = day + dt.timedelta(hours=h)
            if start < t < end:
                x = x_at((t - start).total_seconds())
                el.append(f'<div class="hourline" style="left:{x:.1f}px;top:{top:.1f}px;height:{plot_bottom - top:.1f}px"></div>')
                if xb - xa > px(200):
                    el.append(f'<div class="hourlabel" style="left:{x:.1f}px;top:{plot_bottom + px(6):.1f}px">{h:02d}</div>')
        day += dt.timedelta(days=1)
        k += 1

    # seat lanes
    for seat in seats:
        y = lane_y[seat]
        el.append(f'<div class="lane" style="left:{left:.1f}px;top:{y:.1f}px;width:{plot_w:.1f}px;height:{lane_h:.1f}px"></div>')
        el.append(f'<div class="seat" style="top:{y + lane_h / 2 - px(18):.1f}px;width:{left - px(28):.1f}px">'
                  f'{html.escape(seat)}</div>')

    # runs: a block per run, a red block plus a triangle for a failure, an open diamond for a locked run
    for i, r in enumerate(ex["runs"]):
        y0 = lane_y.get(r["seat"], top)
        mid = y0 + lane_h * 0.62
        x0 = x_at(r["start_s"])
        t0 = round(t_at(r["start_s"]), 3)
        if r["status"] == "locked":
            d = px(22)
            el.append(f'<div id="r{i}" class="lock" style="left:{x0 - d / 2:.1f}px;top:{y0 + lane_h * 0.2 - d / 2:.1f}px;'
                      f'width:{d:.1f}px;height:{d:.1f}px"></div>')
            tw.append(f'tl.fromTo("#r{i}",{{opacity:0,scale:2.2,rotation:45}},{{opacity:1,scale:1,rotation:45,duration:0.35,ease:"power3.out"}},{t0});')
            continue
        w = max(px(MIN_BLOCK), x_at(r["end_s"]) - x0)
        failed = r["status"] != "ok"
        color = FAIL if failed else KIND_COLOR.get(r["kind"], DIM)
        el.append(f'<div id="r{i}" class="run" style="left:{x0:.1f}px;top:{mid - bar_h / 2:.1f}px;width:{w:.1f}px;'
                  f'height:{bar_h:.1f}px;background:{color}"></div>')
        tw.append(f'tl.fromTo("#r{i}",{{opacity:0,scaleY:0.2}},{{opacity:1,scaleY:1,duration:0.3,ease:"power3.out"}},{t0});')
        if failed:
            tri = px(26)
            el.append(f'<div id="f{i}" class="fail" style="left:{x0 + w / 2 - tri / 2:.1f}px;top:{y0 + lane_h * 0.2 - tri / 2:.1f}px;'
                      f'border-left-width:{tri / 2:.1f}px;border-right-width:{tri / 2:.1f}px;border-top-width:{tri:.1f}px"></div>')
            tw.append(f'tl.fromTo("#f{i}",{{opacity:0,y:-{px(20)}}},{{opacity:1,y:0,duration:0.35,ease:"back.out(2)"}},{t0});')

    # the key: kinds present, then the two marks
    key = [f'<span class="kk"><i style="background:{KIND_COLOR[k]}"></i>{k}</span>' for k in ex["kinds"]]
    if tot["failed"]:
        key.append(f'<span class="kk"><b class="fail key"></b>failed</span>')
    if tot["locked"]:
        key.append('<span class="kk"><b class="lock key"></b>gave up waiting for the seat</span>')

    # running counts: computed from the timeline's own time, so any frame can be rendered alone
    runs_js = json.dumps([[r["start_s"], r["end_s"]] for r in ex["runs"]])
    data = {"title": title, "range": fmt_range(start, end), "subset": subset_line(ex)}
    close_lines = [
        f'{tot["ok"]} ok, {tot["failed"]} failed, {tot["locked"]} gave up waiting',
        f'{hours_text(tot["seconds"])} hours of runs ({tot["minutes"]:.1f} minutes) on {plural(len(ex["seats"]), "seat")}',
    ]

    return f"""<!doctype html>
<!-- Built by build.py from one week export. Edit build.py, not this file. -->
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; overflow: hidden; background: {BG}; }}
      #root {{ position: relative; width: {width}px; height: {height}px; background: {BG};
              font-family: Inter, sans-serif; color: {INK}; font-variant-numeric: tabular-nums; }}
      #stage {{ position: absolute; inset: 0; }}
      #stage div, #stage b {{ position: absolute; }}
      .band {{ background: #171b21; }}
      .lane {{ border-top: {px(2)}px solid {FAINT}; border-bottom: {px(2)}px solid {FAINT}; }}
      .dayline {{ width: {px(2)}px; background: {FAINT}; }}
      .hourline {{ width: 1px; background: #232830; }}
      .daylabel {{ font-size: {px(30)}px; font-weight: 700; color: {DIM}; }}
      .hourlabel {{ font-size: {px(28)}px; color: #6b7480; transform: translateX(-50%); }}
      .seat {{ left: 0; text-align: right; font-size: {px(32)}px; font-weight: 700; color: {INK}; }}
      .run {{ border-radius: {px(3)}px; transform-origin: 50% 50%; }}
      .fail {{ width: 0; height: 0; border-style: solid; border-color: {FAIL} transparent transparent transparent; }}
      .lock {{ border: {px(4)}px solid {LOCK}; }}
      #head {{ position: absolute; left: {px(70)}px; top: {px(56)}px; right: {px(560)}px; }}
      #title {{ font-size: {px(60)}px; font-weight: 900; letter-spacing: -0.01em; }}
      #range {{ font-size: {px(34)}px; color: {DIM}; margin-top: {px(10)}px; }}
      #subset {{ position: absolute; left: {px(70)}px; top: {px(192)}px; font-size: {px(28)}px; color: {DIM}; }}
      #count {{ position: absolute; right: {px(70)}px; top: {px(56)}px; text-align: right; }}
      #count .n {{ font-size: {px(64)}px; font-weight: 900; line-height: 1; }}
      #count .l {{ font-size: {px(28)}px; color: {DIM}; margin-top: {px(6)}px; }}
      #count .c {{ display: inline-block; margin-left: {px(48)}px; }}
      #key {{ position: absolute; left: {px(70)}px; bottom: {px(70)}px; font-size: {px(28)}px; color: {DIM};
              display: flex; flex-wrap: wrap; gap: {px(14)}px {px(40)}px; right: {px(70)}px; }}
      .kk {{ display: inline-flex; align-items: center; gap: {px(12)}px; }}
      .kk i {{ display: inline-block; width: {px(30)}px; height: {px(16)}px; border-radius: {px(3)}px; }}
      #key b.key {{ position: relative; }}
      #key b.fail {{ border-left-width: {px(12)}px; border-right-width: {px(12)}px; border-top-width: {px(22)}px; }}
      #key b.lock {{ width: {px(18)}px; height: {px(18)}px; margin: 0 {px(3)}px; transform: rotate(45deg); }}
      #playhead {{ position: absolute; left: {left:.1f}px; top: {top - px(14):.1f}px; width: {px(3)}px;
                   height: {plot_bottom - top + px(28):.1f}px; background: {INK}; }}
      #close {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
                justify-content: center; text-align: center; }}
      #c-inner {{ display: flex; flex-direction: column; align-items: center; }}
      #close .big {{ font-size: {px(150)}px; font-weight: 900; line-height: 1; }}
      #close .line {{ font-size: {px(44)}px; margin-top: {px(22)}px; }}
      #close .sub {{ font-size: {px(30)}px; color: {DIM}; margin-top: {px(40)}px; max-width: {px(1400)}px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{LENGTH}" data-fps="{FPS}"
         data-width="{width}" data-height="{height}">
      <div id="stage" class="clip" data-start="0" data-duration="{CLOSE + 0.5}" data-track-index="1">
        {"".join(el)}
        <div id="playhead"></div>
      </div>
      <div id="head" class="clip" data-start="0" data-duration="{LENGTH}" data-track-index="2">
        <div id="title">{html.escape(data["title"])}</div>
        <div id="range">{html.escape(data["range"])}</div>
      </div>
      <div id="subset" class="clip" data-start="0" data-duration="{CLOSE + 0.5}" data-track-index="3"><span id="subset-t">{html.escape(data["subset"])}</span></div>
      <div id="count" class="clip" data-start="0" data-duration="{CLOSE + 0.5}" data-track-index="4">
        <span class="c"><div class="n" id="n-runs">0</div><div class="l">runs</div></span>
        <span class="c"><div class="n" id="n-hours">0.0</div><div class="l">hours</div></span>
      </div>
      <div id="key" class="clip" data-start="0" data-duration="{CLOSE + 0.5}" data-track-index="5">{"".join(key)}</div>
      <div id="close" class="clip" data-start="{CLOSE}" data-duration="{LENGTH - CLOSE:.1f}" data-track-index="6">
        <div id="c-inner">
        <div class="big" id="c-big">{html.escape(plural(tot["runs"], "run"))}</div>
        <div class="line" id="c-l1">{html.escape(close_lines[0])}</div>
        <div class="line" id="c-l2">{html.escape(close_lines[1])}</div>
        <div class="sub" id="c-sub">{html.escape(data["subset"])}</div>
        </div>
      </div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const RUNS = {runs_js}, SPAN = {span}, A = {SWEEP[0]}, B = {SWEEP[1]};
      const nRuns = document.getElementById("n-runs"), nHours = document.getElementById("n-hours");
      function counts(t) {{   // t: timeline seconds; the window time the playhead has reached
        const w = Math.max(0, Math.min(1, (t - A) / (B - A))) * SPAN;
        let n = 0, s = 0;
        for (const [a, b] of RUNS) {{ if (a <= w) {{ n++; s += Math.min(w, b) - a; }} }}
        nRuns.textContent = String(n);
        nHours.textContent = (s / 3600).toFixed(1);
      }}
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#title", {{ opacity: 0, y: {px(24)} }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }}, 0.2);
      tl.fromTo("#range", {{ opacity: 0, y: {px(16)} }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }}, 0.45);
      tl.fromTo("#subset-t", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6, ease: "power2.out" }}, 0.9);
      tl.fromTo("#playhead", {{ x: 0 }}, {{ x: {plot_w:.1f}, duration: B - A, ease: "none" }}, A);
      tl.fromTo("#playhead", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.3 }}, B);
      const clock = {{ t: 0 }};
      tl.fromTo(clock, {{ t: 0 }}, {{ t: {LENGTH}, duration: {LENGTH}, ease: "none", onUpdate: () => counts(clock.t) }}, 0);
      {"".join(tw)}
      tl.fromTo(["#stage", "#subset", "#count", "#key"], {{ opacity: 1 }}, {{ opacity: 0, duration: 0.4, ease: "power2.in" }}, {CLOSE});
      tl.fromTo("#c-big", {{ opacity: 0, y: {px(30)} }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }}, {CLOSE + 0.1});
      tl.fromTo("#c-l1", {{ opacity: 0, y: {px(20)} }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }}, {CLOSE + 0.45});
      tl.fromTo("#c-l2", {{ opacity: 0, y: {px(20)} }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }}, {CLOSE + 0.7});
      tl.fromTo("#c-sub", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, {CLOSE + 1.1});
      tl.fromTo("#c-inner", {{ scale: 1 }}, {{ scale: 1.045, duration: {LENGTH - CLOSE:.1f}, ease: "none" }}, {CLOSE});
      counts(0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="a file written by `lanes report --export`")
    ap.add_argument("--title", default="A week of runs")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--out", default=os.path.join(HERE, "build"), help="folder for index.html (default: build/ here)")
    a = ap.parse_args(argv)
    with open(a.export) as f:
        ex = json.load(f)
    if ex.get("format") != "lanes-week-export/1":
        sys.exit(f"build.py: {a.export} is not a lanes week export")
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, "index.html")
    with open(out, "w") as f:
        f.write(build(ex, a.title, a.width, a.height))
    print(f"wrote {out}: {len(ex['runs'])} runs, {len(ex['seats'])} seat(s), {LENGTH:.0f} s at {FPS} fps, "
          f"{a.width}x{a.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
