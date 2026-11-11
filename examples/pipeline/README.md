# The pipeline: source, pick, strike, follow up

Outreach where the agent does the research and the drafting and the human does every send.
Three lanes and one human step:

```
pipeline-source   (timer, fortnightly)  finds candidates, qualifies them, files ONE pick list
        |
   the human      comments the numbers on the pick list and approves it
        |
pipeline-strike   (by hand, after a pick)  one draft per pick, in the mail client; nothing sent
        |
   the human      reads each draft and sends it
        |
pipeline-followup (timer, Tue and Fri)  follow-up 1 at day 4, follow-up 2 at day 10,
                                        closed at day 21; drafts only
```

State lives in two places, on purpose:

- `pipeline/tracker.csv` holds one row per target and its status:
  `identified`, `drafted`, `contacted`, `replied`, `dead`.
- **The mailbox is the record of touches.** A row that says `contacted` does not prove a
  pitch went out. The follow-up lane checks Sent before it drafts anything, because the human
  is the one who sends and humans forget to update trackers.

`prospects.example.md` shows what the source lane leaves. The names in it are invented.

Start the strike lane with the picks:

```
LANE_INPUT="D-12: 1 3 4" bin/lane-run.sh outreach pipeline-strike
```

The pick list carries the `outreach` label and the dispatcher example watches `product`, so
the dispatcher never works a pick list. The strike lane owns it.

The outreach seat's mail connector should be able to read the mailbox and create drafts,
and nothing more.
