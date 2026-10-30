#!/usr/bin/env bash
# The reviewer's session, run as the reviewer (ondra) under the review's time
# limit by review-in-sandbox.sh. pi works until it says it is done; then, while
# testing budget and time are left, the same conversation is sent back: first
# to whatever of the inventory it hasn't covered (coverage.py), then, with all
# of it covered, deeper (unconfirmed findings run, screens, hostile inputs).
#
# Three WhisperBox reviews (2026-10-29/30) each stopped by themselves at under
# half their budget, having read 16-22 of the files, a different sample each
# time; a model's own "done" is not the end of an audit.
#
#   review-loop.sh <model> <focus>
# Exit 3: stopped by its budget or time (the write-up pass follows); 0: it
# stopped making progress with budget left.
set -u
MODEL=$1; FOCUS=$2
INV=/run/inventory.json; COV=/run/src/coverage.json
read -r T0 MAX < /run/logs/clock
spent() { python3 -c 'import json;d=json.load(open("/run/logs/spend.json"));print(d["spent"],d["testing"])' 2>/dev/null || echo "0 1"; }
out_of_budget() { [ -s /run/logs/budget-spent-testing.txt ] && return 0; read -r s t < <(spent); python3 -c "import sys;sys.exit(0 if $s >= 0.95*$t else 1)"; }
# The write-up gets the last 25 minutes, after the time limit stops this.
out_of_time() { [ $(( ($(date +%s) - T0) / 60 )) -ge $(( MAX - 8 )) ]; }

pi --model "venice/$MODEL" -p "Your instructions are in /pipeline/reviewer-prompt.md. Read all of it first, then do what it says. This review's focus is \"$FOCUS\": /pipeline/focus/$FOCUS.md says what that covers, and /run/inventory.json lists what you must cover."
round=0; idle=0
while :; do
  out_of_budget && { echo "review-loop: testing budget spent after $round rounds"; exit 3; }
  out_of_time && { echo "review-loop: time used after $round rounds"; exit 3; }
  round=$((round+1)); [ "$round" -gt 40 ] && { echo "review-loop: 40 rounds"; exit 3; }
  read -r s t < <(spent)
  left=$(python3 -c "print(f'{$t-$s:.2f}')"); mins=$(( MAX - ($(date +%s) - T0) / 60 ))
  missing=$(python3 /pipeline/coverage.py "$INV" "$COV" --missing 30)
  if python3 /pipeline/coverage.py "$INV" "$COV" --json | python3 -c 'import json,sys;sys.exit(0 if json.load(sys.stdin)["missing"] else 1)'; then
    msg="You stopped, but the review is not finished: $left DIEM of the testing budget and about $mins minutes are left, and the inventory is not covered yet:
$missing
Carry on: cover these, most exposed first: read each one through, test what it does with hostile input, and mark it in /run/src/coverage.json as the instructions say (status, the line ranges you read, what you checked, the FR ids it led to). Add each finding to report.md and report.json as you go. Don't stop while items are left and budget remains."
  else
    msg="The inventory is covered ($left DIEM and about $mins minutes left). Go deeper with what is left, in this order: turn every [read] finding into [run] with a probe; for each finding, look for its siblings (the same mistake elsewhere); attack the most exposed entry points again with inputs you haven't tried; and, if the focus includes the UI, every screen in Basecamp with hostile input. Keep report.md, report.json and coverage.json current. Don't stop while budget remains."
  fi
  before=$s
  pi --continue --model "venice/$MODEL" -p "$msg"
  read -r s t < <(spent)
  # A round that spent nothing: pi is failing, not reviewing.
  if python3 -c "import sys;sys.exit(0 if $s - $before < 0.002 else 1)"; then
    idle=$((idle+1)); [ "$idle" -ge 2 ] && { echo "review-loop: two rounds without progress"; exit 0; }
  else idle=0; fi
done
