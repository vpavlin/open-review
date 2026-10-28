#!/usr/bin/env bash
# Review one Basecamp module, end to end. Runs on the review host as the
# reviewer user. One task = one review (open-review PoC, ADR-072).
#
#   review.sh <repo-url> [<commit>] [<lgx-url>]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=/home/reviewer/.review

# One review at a time, and a review runs from its own copy of the pipeline.
# On 2026-10-28 a deploy rewrote review-in-sandbox.sh under a sandbox still
# executing it (bash reads a script as it goes: "syntax error near
# unexpected token do"), and that sandbox had outlived a stop whose pkill -f
# matched the stopping shell itself.
if [ -z "${REVIEW_SNAPSHOT:-}" ]; then
  mkdir -p "$STATE"
  exec 9>"$STATE/lock"
  flock -n 9 || { echo "a review is already running (review-stop.sh ends it)"; exit 1; }
  # Whatever an earlier, interrupted review left: no review holds the lock now.
  for c in $(podman ps -q --filter ancestor=localhost/open-reviewer:latest); do podman kill "$c" >/dev/null; done
  SNAP=$STATE/pipeline-$(date -u +%Y%m%d-%H%M%S)
  cp -a "$HERE" "$SNAP"
  ls -d "$STATE"/pipeline-* | head -n -5 | xargs -r rm -rf
  echo $$ > "$STATE/pid"
  REVIEW_SNAPSHOT=1 exec bash "$SNAP/review.sh" "$@"
fi
IMG=localhost/open-reviewer:latest
BASECAMP=/home/reviewer/sandbox/Basecamp.AppImage
REPO=${1:?repo url}; COMMIT=${2:-HEAD}; LGX=${3:-}
slug=$(printf '%s-%s' "$(basename "$REPO" .git)" "${COMMIT:0:12}" | tr -c 'A-Za-z0-9._-' -)
RUN=/home/reviewer/runs/$slug; rm -rf "$RUN"; mkdir -p "$RUN"/{src,checks,build,behaviour,media,logs}
DEST=/srv/reviews/$slug
# A review of the same commit again: the last one stays published beside it,
# named for when it ran. Overwriting in place left the earlier run's report
# showing on a run that never wrote one (forumer, 2026-10-27).
if [ -e "$DEST/index.html" ]; then mv "$DEST" "$DEST-$(date -u -r "$DEST/index.html" +%Y%m%d-%H%M)"; fi
rm -rf "$DEST"; mkdir -p "$DEST"
log(){ printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$RUN/logs/pipeline.log"; }
live(){ printf '%s\n' "$*" >> "$RUN/live.txt"; "$HERE/render.py" "$RUN" "$DEST" "$slug" live >/dev/null 2>&1 || true; }
inbox(){ podman run --rm --network "$1" -v "$RUN:/run:z" -w /run "$IMG" bash -lc "$2"; }

: > "$RUN/live.txt"; live "# Reviewing $REPO @ $COMMIT"; live "starting…"
log "review $REPO @ $COMMIT -> $RUN ; live at ${REVIEW_BASE:-http://REVIEW-HOST}/$slug/live.html"

live "## clone"; log "clone"
if [[ "$REPO" == localdir:* ]]; then
  cp -a "${REPO#localdir:}/." "$RUN/src/" 2>/dev/null; echo "localdir" > "$RUN/logs/commit"
else
inbox bridge "git clone --quiet --filter=blob:none '$REPO' src 2>&1 | tail -3; cd src && git checkout --quiet '$COMMIT' 2>/dev/null; git rev-parse HEAD > /run/logs/commit 2>/dev/null; true"
fi
echo "$REPO" > "$RUN/logs/repo"

# The published package, if there is one: the reviewer installs this into
# Basecamp, so what is tested is what users install.
if [ -n "$LGX" ]; then
  live "## fetch the published package"; log "lgx $LGX"
  mkdir -p "$RUN/lgx"
  inbox bridge "curl -sSfL --max-time 300 -o 'lgx/$(basename "$LGX")' '$LGX' && sha256sum lgx/*.lgx > logs/lgx.sha256" \
    || live "  could not download $LGX"
  [ -s "$RUN/logs/lgx.sha256" ] && live "  $(cat "$RUN/logs/lgx.sha256")"
  # What it needs, from the official catalogue, fetched here so the sandbox's
  # record of hosts contacted stays the module's own.
  for l in "$RUN"/lgx/*.lgx; do
    [ -f "$l" ] && "$HERE/fetch_deps.py" "$l" "$RUN/lgx/deps" "$HOME/lgx-cache" 2>&1 | while read -r d; do live "  dependency: $d"; done
  done
fi

live "## static checks (gitleaks, osv-scanner, semgrep)"; log "static"
inbox bridge 'cd src
  gitleaks detect --no-banner --report-format json --report-path /run/checks/gitleaks.json . >/dev/null 2>&1 || true
  osv-scanner --format json --recursive . > /run/checks/osv.json 2>/dev/null || true
  semgrep scan --quiet --json --config auto . > /run/checks/semgrep.json 2>/dev/null || true
  true'
for c in gitleaks osv semgrep; do [ -s "$RUN/checks/$c.json" ] && live "  $c: $(wc -c < "$RUN/checks/$c.json") bytes"; done

live "## review: build, run and attack it in the sandbox (this is the work)"; log "sandboxed review"
"$HERE/reviewer.sh" "$RUN" 2>&1 | tail -6 | tee -a "$RUN/logs/pipeline.log"
python3 - "$RUN/behaviour/summary.json" <<'PY2' | while read l; do live "  $l"; done
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 if d.get("bait_files_read"): print("bait read during review: "+", ".join(d["bait_files_read"]))
 if d.get("contacted_hosts"): print("hosts contacted: "+", ".join(d["contacted_hosts"]))
except Exception: pass
PY2

# A review whose model failed, or that wrote no report, is a failed review,
# never a quiet one: published as failed, with no verdict.
if [ -s "$RUN/logs/sandbox-check-failed.txt" ]; then
  cp "$RUN/logs/sandbox-check-failed.txt" "$RUN/logs/failed.txt"
elif [ -s "$RUN/logs/inference-failed.txt" ]; then
  { echo "The model provider failed and kept failing, so the review could not be done:"; cat "$RUN/logs/inference-failed.txt"; } > "$RUN/logs/failed.txt"
elif [ ! -s "$RUN/report.md" ]; then
  echo "The reviewer wrote no report (see session.log for how it ended)." > "$RUN/logs/failed.txt"
fi
[ -s "$RUN/logs/failed.txt" ] && { log "FAILED: $(head -1 "$RUN/logs/failed.txt")"; live "## REVIEW FAILED"; live "$(cat "$RUN/logs/failed.txt")"; }

log "publish"; "$HERE/render.py" "$RUN" "$DEST" "$slug" final 2>&1 | tee -a "$RUN/logs/pipeline.log"
log "done -> ${REVIEW_BASE:-http://REVIEW-HOST}/$slug/"
