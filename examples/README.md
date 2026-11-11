# Example lanes

Generic templates. Each folder holds the lane prompt and the systemd units that schedule it.
The paths in the units assume the repo is cloned to `~/headless-lanes`.

| Example | Lanes | Shows |
|---|---|---|
| `weekly-digest/` | `weekly-digest` | Read-only reporting. Files a decision only when one is needed. |
| `dispatcher/` | `dispatcher` | Approve, then dispatch. `ExecCondition=` skips the run when nothing is approved. |
| `pipeline/` | `pipeline-source`, `pipeline-strike`, `pipeline-followup` | Outreach in four steps: source, pick (the human), strike, follow up. The agent drafts and the human sends. |

To install one:

```
cp examples/weekly-digest/weekly-digest.md lanes/
# add the [lanes.weekly-digest] block to lanes/lanes.toml
bin/lane-run.sh main weekly-digest                 # once, in the foreground; read the log
ln -sf ~/headless-lanes/examples/weekly-digest/lane-weekly-digest.{service,timer} ~/.config/systemd/user/
ln -sf ~/headless-lanes/systemd/lane-failed@.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now lane-weekly-digest.timer
```

The prompts name scripts and folders (`scripts/fetch-metrics.sh`, `reports/`, `pipeline/`)
that are yours to supply. Replace them before the first run.
