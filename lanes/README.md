# Lanes

A lane is a markdown file and a timer. The file is the whole prompt for one headless
`claude -p` run. The timer decides when.

```
bin/lane-run.sh <seat> <lane>     # runs lanes/<lane>.md under that seat's login
```

The runner takes the seat's lock (one run per seat at a time), unsets the API key so the run
bills the seat, runs the prompt, and writes one row to the run log whether or not the run
ended ok. A run that did not end ok is also put in the inbox. A file named `STOP` beside the
database pauses every lane, and `<lane>.STOP` pauses one.

## What a lane prompt says

Four things, in this order. The examples in `../examples/` all follow it.

1. **Who it is, and that nobody is watching.** "You are the `main` seat, running headless on
   a Monday morning. Nobody is watching." A headless run that thinks someone will answer a
   question stalls on the question.
2. **The job.** Numbered steps, with the files to read and the commands to run. Say what to
   do when a step fails. "If the script exits non-zero, stop: no partial report."
3. **The hard limits.** What it must never touch, and that nothing is sent. Repeat them in
   every prompt. A headless run starts with its prompt and the project's files and nothing
   else.
4. **The one thing it finishes with.** A file registered in the inbox, or one decision in the
   queue, plus the fallback when a connector is missing. One artifact per run keeps the
   output findable.

## Rules that go in every lane

- **Register what you make, in the step that makes it:**
  `lanes deliver <lane> <kind> <path|url> title="..."`. Kinds: draft, batch, prospects,
  report, digest, guide, other. The kind sets what the human has to do with it (drafts,
  batches and prospects need action; reports and digests are FYI). Pass `needs=` when the
  default is wrong.
- **File a decision only when a human must decide:**
  `lanes queue add <label> "<title>" --body-file <file>`. The body says what approval means.
  Then tie the file to it: `lanes deliver ... decision=D-n`. Registering a file a second
  time updates its row and keeps the title.
- **Nothing is sent.** A send is a draft. A merge is a PR.
- **Carry a fallback.** If the mail or tracker connector is missing in this run, write the
  same content into the report and say so in the first line of the final output.

## Input from the caller

`LANE_INPUT="D-12: 1 3 4" bin/lane-run.sh outreach pipeline-strike` appends the text to the
prompt under a `## Input from the caller` heading. That is how a human's picks reach a lane.

## Adding a lane

1. Write `lanes/<name>.md`.
2. Add a `[lanes.<name>]` block to `lanes.toml` (seat, and `cadence_days` if it is scheduled).
3. Run it once in the foreground: `bin/lane-run.sh <seat> <name>`. Read the log. The seat
   must be logged in, and its connectors must come up in headless mode.
4. Copy a unit pair from `../systemd/`, point it at the lane, and enable the timer.

This folder ships with no lanes. Copy the ones you want from `../examples/`.
