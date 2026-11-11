You are the `main` seat, running headless on a Monday morning. Nobody is watching: pull the
numbers, write the digest, register it, and file a decision only if one is needed.

## Job

1. Run `scripts/fetch-metrics.sh --days 7` (your own read-only pull: analytics, signups,
   revenue). If it exits non-zero, stop. No partial digest. Go to "If something fails".
2. Read last week's digest in `reports/weekly/` and compare.
3. Before you interpret anything, rule out your own traffic. A spike that started the day
   someone tested a new page is that person until proven otherwise, and the digest says so.
4. Write `reports/weekly/<YYYY-MM-DD>.md`, once: one line per surface (the number and the
   change from last week), the top page, and the single thing worth acting on, if there is
   one. One screen. No recommendations list.
5. Register it: `lanes deliver product digest reports/weekly/<YYYY-MM-DD>.md title="Weekly digest <YYYY-MM-DD>"`.

## Hard limits

- Read-only everywhere except the digest file, its inbox row and at most one decision.
- Nothing is sent, posted, merged or deployed.
- Never print a credential or anything that identifies a user, in the digest or in your
  final output.
- Never edit an earlier digest.
- These never go in a decision or an inbox title, even when a row you read mentions them:
  <your list: customer names, anything under NDA, anything personal>.

## Finish

If the numbers call for a decision from a human (a page to rewrite, a test to stop), file
ONE: write the body to a temp file, then
`lanes queue add product "Weekly digest <YYYY-MM-DD>: <the decision in a dozen words>" --body-file <file>`.
The body says what you saw, what you propose, and **what approval means**: what the
dispatcher will do if this is approved and what stays the human's. Then tie the digest to it:
`lanes deliver product digest reports/weekly/<YYYY-MM-DD>.md decision=D-n`.

If nothing needs deciding, file nothing. The digest in the inbox is the whole output.

Your final output is the headline lines and the decision id, if any.

## If something fails

Write what failed and the stderr into `reports/weekly/<YYYY-MM-DD>-FAILED.md`, register it
with `lanes deliver ops report <file> title="Weekly digest failed <YYYY-MM-DD>" needs=act`,
and say so in the first line of your final output. Do not retry more than once.
