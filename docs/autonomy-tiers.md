# Autonomy tiers

Every piece of work an agent can do falls in one of three tiers. The question that sorts them
is simple: can it be undone without anyone outside noticing?

## Tier 1: just do it, then report

Research, sourcing, drafts, database writes, queued builds, cleanup, code on a branch.

All of it is reversible and none of it leaves the machine. The agent does the work and the
report is the inbox row. Nobody is asked first.

## Tier 2: one tap from the human

Anything that leaves the building: sending an email, posting, merging to a production branch,
deploying, spending money, creating an account.

The agent does everything up to the tap. A send is a draft sitting in the right mailbox. A
merge is an open PR. A purchase is a decision in the queue with the price in it. The human's
part should take seconds, and it should be obvious what happens when they do it.

## Tier 3: human only

Phone calls, legal and financial filings, anything that speaks for the person in a way that
can't be taken back. The agent can prepare for these. It never does them, and no approval
changes that.

## How the tiers are enforced

A rule in a prompt is a request. These are the things that make the request hold.

**The prompt names its limits.** Every lane prompt has a "Hard limits" section that says what
the lane must never touch and that nothing is sent. Limits go in every prompt, even when they
repeat, because a headless run starts with nothing but its prompt and the project's files.

**The seat can't do it anyway.** A seat only gets the connectors its lanes need. A drafting
lane's mail connector can create drafts. If a lane has no business merging, its seat has no
merge rights. When the prompt and the permissions disagree, the permissions win, so set those
first.

**The lane ends before the tap.** Each lane finishes with exactly one artifact: a file in the
inbox, a draft, a PR, or a decision in the queue. "Done" for a Tier 2 job means "ready for
the tap", and the lane's final output says which tap is the human's.

**Exceptions are written down.** Some Tier 2 work can earn a standing approval. Each one is
recorded with its scope, its cap, the date, and the words the human used to grant it. An
exception with no cap is a hole in the tier.

**Caps are constants.** In my own system, a cap per run and a cap per day live in code as
named constants. The agent can read them and can't change them, because changing one takes a
commit by the human. The same rule covers money: the one place that system touches an
exchange, the order size and the loss floor are constants in the script. This repo ships one
cap of that kind, the dispatcher's three decisions a run, and it lives in the prompt.

**There is a kill switch, and it is a file.** The runner checks for it before it takes a
seat: `touch ~/.local/share/headless-lanes/STOP` pauses every lane, and `<lane>.STOP` in the
same folder pauses one. A skipped run wakes no seat. The lint warns while a switch is on, so
it can't be forgotten. It is a file because a file works from a phone over SSH, survives a
reboot, and needs no running service to honor it.

## The decision queue

The queue is where Tier 2 work waits. It stays useful only while it stays short, so:

- **An agent files a decision only when it needs a human.** A weekly report that found
  nothing files nothing. The record of what ran belongs in the run log.
- **The title says the decision.** `[label] what: the choice`, readable in a list.
- **The body says what approval means.** One paragraph, in bold if it helps: what the
  dispatcher will do when this is approved, and what stays the human's. If the agent can't
  write that paragraph, the decision isn't ready to file.
- **One decision per choice.** A pick list is one decision; the picks go in a comment.

States: `todo` (waiting on the human), `in_progress` (approved, or being worked), `done`,
`declined`. An approval is the only way into `in_progress`, whether it is made in the console,
with `lanes queue approve`, or in the mirrored tracker and copied in by `lanes queue pull`.

## The dispatcher contract

A dispatcher lane works approved decisions. Its rules:

1. Work only what `lanes dispatch-check` lists. Never touch a decision in any other state.
2. At most three per run, oldest approval first. The rest wait.
3. Read the whole decision and every comment. The newest human comment overrides the body.
4. Stay inside Tier 1. When the approved work ends in a Tier 2 action, stop at the draft or
   the PR and say exactly which tap is the human's.
5. Comment on the decision. The comment starts with `**Dispatch (seat, date time)**` and says
   what was done, where it is, and the one thing the human does next.
6. Move it: `done` when nothing is left for the human, back to `todo` when the next step is
   theirs, or leave it `in_progress` with `[continuing]` in the comment when the work needs
   another run.
7. If the approval is ambiguous, don't guess. Comment the question with the options and a
   recommendation, and hand it back.

`dispatch-check` enforces the other half. A decision the dispatcher already answered is not
listed again until the human replies on it or approves it again, so the dispatcher never
works the same answer twice.
