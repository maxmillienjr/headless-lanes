# Guardrails, and the failure behind each one

Every guardrail here came from something breaking in the system this repo was cut from. I've
kept the failures in, because a guardrail without its failure reads like superstition and gets
deleted in the next cleanup.

## 1. A cloud-drive mount zeroed a file. Twice, same day.

**What happened.** My working files live on a cloud drive mounted over FUSE. In-place
rewrites of a long document there (the `sed -i`, scripted-rewrite and shell-redirect kind of
edit) left the file at zero bytes. It happened twice in one day.

**The guardrail.**

- A write protocol for anything on the mount: edit a scratch copy on local disk, verify it,
  one atomic `cp` onto the mount, verify again, then a dated backup. The lane prompts that
  write there ban in-place edits by name.
- The database never lives on the mount. SQLite on FUSE or a network filesystem corrupts,
  because the locking it depends on is advisory at best there. The database sits on local
  disk and a verified backup is copied to the mount.

**In this repo.** `connect()` in `bin/lanes` checks the filesystem under the database path
and refuses to open it on a FUSE or network mount. `tests/test_lint.py` covers the check.

## 2. Hooks crashed on a second machine and seeded an empty database.

**What happened.** I started using a laptop as a second client. The session-start hooks
crashed there and seeded an empty local database.

**The guardrail.** One hub machine holds the database, the mount and the timers. Every other
machine is a thin client that runs the real thing on the hub over SSH. The hook wrapper does
that hop itself, and the connect call refuses to run on the client's OS at all.

**In this repo.** `hooks/session-digest.py` never creates a database. If the file isn't
there it prints one line saying so and exits 0. It also never blocks a session: any failure
degrades to a single line of output. `lanes seed-demo` has the same manners: it writes only
inside the folder it is given, never to the real database.

## 3. An API key in a shell rc file changed how everything was billed.

**What happened.** An API key was left in a shell rc file. With it set, Claude Code bills
per token instead of using the seat's subscription, and the phone remote control stops
working.

**The guardrail.** The key has exactly one job and it is passed to that job directly. It
never goes in an rc file.

**In this repo.** The runner starts every lane with `env -u ANTHROPIC_API_KEY -u
ANTHROPIC_AUTH_TOKEN`, so a stray key can't change the billing of an unattended run.
`tests/test_runner_lock.py` sets the key in the parent environment and checks the lane never
sees it.

## 4. The tracker's free plan stops creating issues past a cap.

**What happened.** In my system, decisions are issues in a hosted tracker. Its free plan
stops creating issues past a fixed count of non-archived ones. A queue that stops accepting
decisions is a bad way for this to fail.

**The guardrail.** Closed issues auto-archive after a month, the count is on the dashboard,
and the rule became: no issue without a decision. A report that needs nothing from me is an
inbox row, and the inbox clears itself.

**In this repo.** The queue is a local SQLite table by default, so the demo and a small
setup need no account anywhere. The hosted tracker is an optional mirror. The rule is in
every example prompt: file a decision only when a human must decide.

## 5. Agents left files nobody tracked.

**What happened.** Lanes left reports, drafts and batches in folders. Nothing tracked what
had been made or whether anyone had read it.

**The guardrail.** Two rules. Anything made for a human is registered in the inbox in the
same step that creates it. And a nightly lint, with no agent involved, checks what the rule
missed: files in the output folders with no inbox row, inbox rows whose file is gone, lanes
past their cadence, runs that failed and never recovered, and headless minutes per seat
against a soft weekly budget.

**In this repo.** `lanes deliver`, `lanes lint`, `lanes nightly`, and the Today page.

## Smaller ones

- **systemd's PATH.** User units get the service manager's PATH, which had no
  `~/.local/bin`. Under a timer, `claude` was not found; from a terminal the same lane ran.
  The runner now sets PATH itself.
- **Connectors are per seat.** The first headless run on a new seat couldn't create a mail
  draft, because the mail connector had not been authorized on that seat. Now a
  lane is run once in the foreground before its timer is enabled, and a prompt that depends
  on a connector carries a file fallback, so a missing connector still leaves a report.
- **A private detail in a ticket.** A weekly report lane copied a detail from a private
  database row into a ticket. A lane that writes to the queue now carries an explicit list
  of what never goes in a decision, even when a row it is summarizing mentions it. The
  example prompts each have the line, with the list left for you to fill in.

## About `--dangerously-skip-permissions`

The runner passes it by default. A headless run has nobody to answer a permission prompt, so
without it most lanes stall on their first tool call.

With that flag on, three other things are the boundary, and all three have to be real:

1. **The seat.** What its login, its connectors and its tokens are allowed to do.
2. **The lane prompt's hard limits.** What it must never touch, and that nothing is sent.
3. **The machine.** The user the timer runs as, and what that user can reach.

If you want a narrower boundary, set `LANE_CLAUDE_FLAGS=` (empty) to drop the flag and put
an allow list after the lane name, where the runner passes arguments through as they are:
`lane-run.sh main weekly-digest --allowedTools "Bash(git status)" Read`. Don't copy the
default into a setup where the seat has permissions you wouldn't hand to a script.
