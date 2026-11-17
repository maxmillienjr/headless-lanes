# Failures, reproduced

Each rule in this repo exists because something broke. [docs/guardrails.md](../docs/guardrails.md)
tells each break in prose. This folder is the part you can run: one small script per break,
which sets up the unsafe condition in a temp folder, shows what goes wrong without the
guardrail, then shows the guardrail catching it.

## Run them

One:

```
python3 failures/03-api-key-switches-billing.py
```

All of them, as a test:

```
python3 -m unittest discover -s tests -p test_failures.py -v
```

or as a plain loop:

```
for f in failures/[0-9]*.py; do python3 "$f" | tail -n 1; done
```

Each script exits 0 only if its guardrail held, and its last line starts with `HELD:` or
`BROKEN:`. They need Python 3.11 or newer, `bash` and `flock`, the same as the runner. They use
no network, no real Claude seat and no real key (the fake ones say so in their value), and
everything they write goes in a temp folder that is deleted when they finish.

## What "reproduction" means here

Some of these breaks can't be recreated safely on your machine. I'm not going to zero a file on
your cloud drive or change how your account is billed. Where that is the case, the script
reproduces the *condition the guardrail checks for*: a database path on a FUSE mount, a key in
the parent environment, a tracker that refuses to create issues. Each script's opening comment
says what is real (the repo's own code, run the way it runs) and what is simulated (the mount,
the tracker, the `claude` binary, which is [tests/fake-claude](../tests/fake-claude)). None of
them is the original event, and none of them pretends to be.

A reproduction that still passes with its guardrail removed proves nothing, so each one was
checked the other way too: comment out the guardrail and the script fails.

## The list

| Failure | Reproduction | Guardrail in the code | Test that guards it |
|---|---|---|---|
| 1. A cloud-drive mount zeroed a file, twice in one day | [01-database-on-a-fuse-mount.py](01-database-on-a-fuse-mount.py) | `connect()` and `fs_type()` in [bin/lanes](../bin/lanes): no database on a FUSE or network mount | [tests/test_lint.py](../tests/test_lint.py) `Database` (the mount parsing); the refusal itself is covered by this script through `tests/test_failures.py` |
| 2. Hooks crashed on a second machine and seeded an empty database | [02-hook-seeds-an-empty-database.py](02-hook-seeds-an-empty-database.py) | `main()` in [hooks/session-digest.py](../hooks/session-digest.py): no database, one line, exit 0; any failure, one line, exit 0 | this script, through `tests/test_failures.py` (`lanes seed-demo`'s matching rule: `tests/test_lint.py` `SeedDemo`) |
| 3. An API key in a shell rc file changed how everything was billed | [03-api-key-switches-billing.py](03-api-key-switches-billing.py) | `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN` in [bin/lane-run.sh](../bin/lane-run.sh) | [tests/test_runner_lock.py](../tests/test_runner_lock.py) `test_the_run_bills_the_seat_not_an_api_key` |
| 4. The tracker's free plan stops creating issues past a cap | [04-tracker-stops-taking-issues.py](04-tracker-stops-taking-issues.py) | the local `decisions` table, and `mirror()` in [bin/lanes](../bin/lanes), which turns a tracker error into one warning | [tests/test_queue.py](../tests/test_queue.py) `test_a_mirror_failure_never_blocks_the_local_write` |
| 5. Agents left files nobody tracked | [05-files-nobody-tracked.py](05-files-nobody-tracked.py) | `stray_files()`, `lint()` and `cmd_nightly()` in [bin/lanes](../bin/lanes) | [tests/test_lint.py](../tests/test_lint.py) `test_a_file_nothing_registered_is_flagged_until_it_is_delivered`, `test_a_row_whose_file_is_gone_is_flagged`, `test_the_nightly_report_is_one_row_however_often_it_warns` |
| systemd's PATH had no `~/.local/bin` | [06-systemd-path-has-no-claude.py](06-systemd-path-has-no-claude.py) | the `export PATH=` line in [bin/lane-run.sh](../bin/lane-run.sh) | this script, through `tests/test_failures.py` |
| Connectors are per seat | none | a practice: run a lane once in the foreground before its timer is on, and give a prompt that needs a connector a file fallback | none; no code can check it |
| A private detail in a ticket | none | a practice: every example prompt in [examples/](../examples) carries a "these never go in" line, with the list left for you to fill in | none; no code can check it |

Two parts of the guardrails doc are practices with no script here, on purpose: the write
protocol for files on the mount (scratch copy, verify, one atomic `cp`, verify, dated backup)
and the rule that no issue is filed without a decision. A script that pretended to check a
habit would be the superstition the doc warns about.

## Yours

If you run agents unattended, you have a failure like these. [CONTRIBUTING.md](CONTRIBUTING.md)
says how to send it with its test.
