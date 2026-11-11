# systemd user units

Everything runs as your own user under `systemctl --user`. Nothing here needs root. The
paths assume the repo is cloned to `~/headless-lanes`; edit `ExecStart=` if it lives
somewhere else.

| File | What |
|---|---|
| `lane-example.service`, `lane-example.timer` | Templates for one lane. The real pairs are in `../examples/`. |
| `lane-failed@.service` | `OnFailure=` handler. Puts the dead run's log in the inbox. |
| `lanes-nightly.service`, `lanes-nightly.timer` | Inbox sweep and lint at 23:00. Plain Python, no Claude seat. |
| `lanes-console.service` | The console, always on, loopback only. |

## Install

Link the units instead of copying them, so the repo stays the source:

```
mkdir -p ~/.config/systemd/user
ln -sf ~/headless-lanes/systemd/lane-failed@.service ~/.config/systemd/user/
ln -sf ~/headless-lanes/systemd/lanes-nightly.{service,timer} ~/.config/systemd/user/
ln -sf ~/headless-lanes/systemd/lanes-console.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lanes-nightly.timer lanes-console.service
loginctl enable-linger "$USER"      # timers keep firing after you log out
```

For each lane, link its `.service` and `.timer` and enable **only the timer**:

```
ln -sf ~/headless-lanes/examples/weekly-digest/lane-weekly-digest.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now lane-weekly-digest.timer
```

A lane with no timer (a by-hand lane like `pipeline-strike`) gets its `.service` linked and
nothing enabled. The console's Run now starts it.

## Before you enable a timer

Run the lane once in the foreground and read the log:

```
~/headless-lanes/bin/lane-run.sh main weekly-digest
```

The seat must be logged in, and its connectors have to come up in headless mode. A connector
you authorized on one seat is not there on another.

## Day to day

```
systemctl --user list-timers 'lane-*'            # next firings
journalctl --user -u lane-weekly-digest -n 40    # the last run's tail
~/headless-lanes/bin/lanes runs                  # the run log
ls ~/.local/share/headless-lanes/logs/main/      # full transcripts
```

## Notes

- **Unit names are `lane-<name>`.** The console finds a lane's next firing by that name, and
  `lane-failed@` strips the prefix to find the log.
- **Dispatchers use `ExecCondition=`.** `lanes dispatch-check <label>` exits 1 when nothing
  is approved. systemd then skips the run as "condition unmet", which is not a failure and
  does not trigger `OnFailure=`. A broken setup exits 255, which does fail the unit. A dispatcher has no `cadence_days` in `lanes.toml` for the
  same reason: a week with nothing approved should not read as a late lane.
- **`Persistent=true` for daily and weekly lanes** so a missed firing runs at the next boot.
  Use `Persistent=false` for anything that fires every few minutes, so a reboot does not set
  off a burst.
- **`TimeoutStartSec=95m`.** The runner can wait 30 minutes for the seat and then run for
  55. The unit has to outlast both, because a run systemd kills writes no row.
- **Environment.** User units do not read your shell rc. That is why the runner sets PATH
  itself, and it is also why an API key exported in an rc file never reaches a timer run.
  The runner unsets the key anyway, for the runs you start by hand.
