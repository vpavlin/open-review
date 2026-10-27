#!/usr/bin/env bash
# Review one Basecamp module, end to end. Runs on the review host as the
# reviewer user. One task = one review (open-review PoC, ADR-072).
#
#   review.sh <repo-url> [<commit>] [<lgx-url>]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
IMG=localhost/open-reviewer:latest
BASECAMP=/home/reviewer/sandbox/Basecamp.AppImage
REPO=${1:?repo url}; COMMIT=${2:-HEAD}; LGX=${3:-}
slug=$(printf '%s-%s' "$(basename "$REPO" .git)" "${COMMIT:0:12}" | tr -c 'A-Za-z0-9._-' -)
RUN=/home/reviewer/runs/$slug; rm -rf "$RUN"; mkdir -p "$RUN"/{src,checks,build,behaviour,media,logs}
DEST=/srv/reviews/$slug; mkdir -p "$DEST"
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

live "## static checks (gitleaks, osv-scanner, semgrep)"; log "static"
inbox bridge 'cd src
  gitleaks detect --no-banner --report-format json --report-path /run/checks/gitleaks.json . >/dev/null 2>&1 || true
  osv-scanner --format json --recursive . > /run/checks/osv.json 2>/dev/null || true
  semgrep scan --quiet --json --config auto . > /run/checks/semgrep.json 2>/dev/null || true
  true'
for c in gitleaks osv semgrep; do [ -s "$RUN/checks/$c.json" ] && live "  $c: $(wc -c < "$RUN/checks/$c.json") bytes"; done

live "## dynamic: build & run in the disguised sandbox, recording everything"; log "dynamic"
BC_MNT=(); [ -x "$BASECAMP" ] && BC_MNT=(-v "$BASECAMP:/opt/basecamp/Basecamp.AppImage:ro")
podman run --rm --hostname dell-xps --cap-add SYS_ADMIN --network bridge \
  -v "$RUN:/run:z" -v "$HERE:/pipeline:ro" "${BC_MNT[@]}" "$IMG" \
  bash /pipeline/dynamic.sh 2>&1 | tail -8 | tee -a "$RUN/logs/pipeline.log"
python3 - "$RUN/behaviour/summary.json" <<'PY' | while read l; do live "  $l"; done
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 if d.get("bait_files_read"): print("BAIT READ: "+", ".join(d["bait_files_read"]))
 if d.get("contacted_hosts"): print("contacted: "+", ".join(d["contacted_hosts"]))
 if d.get("read_secret_then_contacted_external_host"): print("!! read a secret, then contacted an external host")
except Exception as e: print("summary: "+str(e))
PY

live "## report: the reviewer reads the evidence"; log "report"
"$HERE/report.sh" "$RUN" "$REPO" "$COMMIT" 2>&1 | tail -4 | tee -a "$RUN/logs/pipeline.log"

log "publish"; "$HERE/render.py" "$RUN" "$DEST" "$slug" final 2>&1 | tee -a "$RUN/logs/pipeline.log"
log "done -> ${REVIEW_BASE:-http://REVIEW-HOST}/$slug/"
