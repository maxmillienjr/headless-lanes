#!/usr/bin/env bash
# lane-run.sh: run one headless Claude Code lane under a seat's own login.
#
#   lane-run.sh <seat> <lane> [extra claude args...]
#     seat  a Claude Code login with its own config dir (lanes.toml [seats], or the convention:
#           main = ~/.claude, anything else = ~/.claude-<seat>)
#     lane  $LANES_DIR/<lane>.md; the file's contents are the whole prompt
#
# What it guarantees:
#   - One run per seat at a time. A second run waits on a flock, then gives up and is logged
#     as `locked`. The lock belongs to this script alone: the agent's child processes don't
#     inherit it, so something the agent left running can't keep the seat busy.
#   - A kill switch. A file named STOP beside the database pauses every lane, <lane>.STOP
#     pauses one: the run is skipped before it takes a seat.
#   - The run bills the seat's subscription. ANTHROPIC_API_KEY is unset on purpose: with it set,
#     `claude -p` bills per token instead.
#   - Every run is one row in the run log (`lanes log-run`), ok or not, including a run that
#     could not start (no prompt, seat not logged in), plus two files in
#     $LANES_LOG_DIR/<seat>/: <lane>-<stamp>.log (stderr, then the final result) and .json (the
#     `--output-format json` envelope: duration, turns, usage, session id).
#   - A run that did not end ok is put in the inbox, so a lane that died overnight is the first
#     thing a human sees.
#
# Env knobs:
#   LANES_DIR        folder of <lane>.md prompts and lanes.toml (default: ../lanes from this script)
#   LANES_DB         the SQLite file (default ~/.local/share/headless-lanes/lanes.db)
#   LANES_LOG_DIR    transcripts (default: logs/ beside the database)
#   LANE_WORKDIR     where claude runs, so that project's CLAUDE.md and skills load
#                    (default: the parent of LANES_DIR)
#   LANE_INPUT       text appended to the prompt under "## Input from the caller" (a human's picks)
#   LANE_LOCK_WAIT   seconds to wait for the seat (default 1800)
#   LANE_TIMEOUT     wall clock for the run (default 55m). Wait plus run is 86 minutes at
#                    most, which is why the units allow 95.
#   LANE_MAX_TURNS   default 200
#   LANE_MODEL       passed as --model when set
#   LANE_CLAUDE_FLAGS  default --dangerously-skip-permissions (nobody is there to answer a
#                    prompt; see docs/guardrails.md before you copy this). Split on spaces.
#                    For arguments with spaces in them, set this empty and put them after
#                    the lane name, where they are passed through quoted.
#   LANE_NO_SUMMARY  set to keep this run's final text out of the database
#   LANE_CLAUDE_BIN  the binary to run (default claude; the tests point it at a stand-in)
set -uo pipefail

usage="usage: lane-run.sh <seat> <lane> [claude args]"
seat=${1:?$usage}
lane=${2:?$usage}
shift 2
name='^[a-z0-9][a-z0-9-]*$'
[[ $seat =~ $name && $lane =~ $name ]] || { echo "lane-run: seat and lane are lowercase letters, digits, hyphens" >&2; exit 2; }

here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# systemd user units get the manager's PATH, which usually has no ~/.local/bin (where claude
# lives). This folder goes on it too, so a lane prompt can say `lanes deliver ...`.
export PATH="$here:$HOME/.local/bin:$PATH"
lanes="$here/lanes"
export LANES_DIR=${LANES_DIR:-$(dirname "$here")/lanes}
export LANES_DB=${LANES_DB:-$HOME/.local/share/headless-lanes/lanes.db}
export LANES_LOG_DIR=${LANES_LOG_DIR:-$(dirname "$LANES_DB")/logs}
workdir=${LANE_WORKDIR:-$(dirname "$LANES_DIR")}
prompt="$LANES_DIR/$lane.md"

if stop=$("$lanes" stopped "$lane"); then
  echo "lane-run: $lane skipped, the kill switch is on ($stop)"
  exit 0
fi

logdir="$LANES_LOG_DIR/$seat"
mkdir -p "$logdir"
stamp=$(date +%Y%m%d-%H%M%S)
log="$logdir/$lane-$stamp.log"
json="$logdir/$lane-$stamp.json"
echo "lane-run: $seat/$lane -> $log"

failed() {  # put a run that did not end ok in front of a human
  "$lanes" deliver ops report "$log" title="Lane failed: $lane ($1, $(date '+%Y-%m-%d %H:%M'))" \
    needs=act source=lane-run >/dev/null 2>&1 || true
}

bail() {  # a run that could not start still gets a row and a place in the inbox
  echo "lane-run: $1" | tee "$log" >&2
  "$lanes" log-run "$seat" "$lane" --log "$log" --status error --started "$(date -Is)" --ended "$(date -Is)" >/dev/null 2>&1 || true
  failed error
  exit "$2"
}

[ -f "$prompt" ] || bail "no prompt at $prompt" 2
[ -d "$workdir" ] || bail "LANE_WORKDIR $workdir is not a directory" 2
cfg=$("$lanes" seat-dir "$seat") || bail "can't resolve seat $seat (is lanes.toml readable?)" 2
if [ -z "${LANE_SKIP_LOGIN_CHECK:-}" ] && [ ! -f "$cfg/.credentials.json" ]; then
  bail "$cfg is not logged in (run: CLAUDE_CONFIG_DIR=$cfg claude, then /login)" 3
fi

# One run per seat at a time: a second timer firing while a run is live waits, then gives up.
exec 9>"$logdir/.seat.lock"
if ! flock -w "${LANE_LOCK_WAIT:-1800}" 9; then
  echo "lane-run: seat $seat is busy (lock held by another run); giving up" | tee "$log" >&2
  "$lanes" log-run "$seat" "$lane" --log "$log" --status locked --started "$(date -Is)" --ended "$(date -Is)" >/dev/null 2>&1 || true
  failed locked
  exit 75
fi

text=$(cat "$prompt")
if [ -n "${LANE_INPUT:-}" ]; then
  text="$text

## Input from the caller

${LANE_INPUT}"
fi

started=$(date -Is)
cd "$workdir" || exit 2
set -f  # LANE_CLAUDE_FLAGS is split on spaces below; never glob it
# 9>&- closes the lock for the child. Only this script holds the seat.
# shellcheck disable=SC2086  # LANE_CLAUDE_FLAGS is split on purpose
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN CLAUDE_CONFIG_DIR="$cfg" \
  timeout -s INT -k 60 "${LANE_TIMEOUT:-55m}" \
  "${LANE_CLAUDE_BIN:-claude}" -p "$text" \
    ${LANE_CLAUDE_FLAGS---dangerously-skip-permissions} \
    --output-format json \
    --max-turns "${LANE_MAX_TURNS:-200}" \
    ${LANE_MODEL:+--model "$LANE_MODEL"} \
    "$@" >"$json" 2>"$log" 9>&-
status=$?
ended=$(date -Is)

case $status in
  0)       st=ok ;;
  124|137) st=timeout ;;
  *)       st=error ;;
esac
# log-run reads the envelope (an is_error envelope turns ok into error), appends the result to
# the log, writes the row, and prints the final status.
st=$("$lanes" log-run "$seat" "$lane" --json "$json" --log "$log" --status "$st" \
       --started "$started" --ended "$ended" ${LANE_NO_SUMMARY:+--no-summary}) || st=error

echo "lane-run: exit $status ($st)"
tail -n 20 "$log"
[ "$st" = ok ] && exit 0
failed "$st"
exit $(( status == 0 ? 1 : status ))
