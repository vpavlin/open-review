#!/usr/bin/env bash
# Review one Basecamp module, end to end. Runs on the review host as the
# reviewer user. One task = one review (open-review PoC, ADR-072).
#
#   review.sh <repo-url> [<commit>] [<lgx-url>…]   (a module and the packages
#                                                  it ships with, e.g. names + names_ui)
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
  # Exit 75 (EX_TEMPFAIL): the queue puts the job back rather than closing it.
  flock -n 9 || { echo "a review is already running (review-stop.sh ends it)"; exit 75; }
  # podman, and the slirp4netns it starts for every rootless container,
  # must not inherit the lock: slirp4netns outlived a stopped review holding
  # it, and killing it to free the lock took the network from every rootless
  # container after (2026-10-30). Exported, so reviewer.sh's podman too.
  podman() { command podman "$@" 9>&-; }; export -f podman
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
REPO=${1:?repo url}; COMMIT=${2:-HEAD}
# Every package given: a module can ship as more than one (LNS: a core module
# and its view, the view depending on the core).
LGX=$(printf '%s\n' "${@:3}")
# The submission's values reach a shell only as variables, and only in the
# shape they should have: they were pasted into "bash -lc" strings, so a
# quote in a URL ran commands on the review host (FR-4, 2026-10-28).
url_ok(){ [[ "$1" =~ ^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~%+@:/-]*)?$ ]]; }
if [[ "$REPO" != localdir:* ]] && ! url_ok "$REPO"; then echo "not a repository URL: $REPO"; exit 2; fi
[[ "$COMMIT" =~ ^([0-9a-f]{7,40}|HEAD)$ ]] || { echo "not a commit: $COMMIT"; exit 2; }
# A package may also be a file the operator put in ~/inputs on this host
# ("localfile:<name>.lgx"): a release that isn't public, such as WhisperBox
# 0.5.0's linux-amd64 build, served only on the publisher's LAN (2026-10-29).
INPUTS=/home/reviewer/inputs
pkg_ok(){ url_ok "$1" || [[ "$1" =~ ^localfile:[A-Za-z0-9._-]+\.lgx$ && -f "$INPUTS/${1#localfile:}" ]]; }
for u in "${@:3}"; do pkg_ok "$u" || { echo "not a package URL: $u"; exit 2; }; done
# What the review covers (inventory.py, focus/*.md): one focus a review, as
# the submitter chooses; a full review gets more budget and time.
FOCUS=${REVIEW_FOCUS:-security}
case "$FOCUS" in security|p2p|ui) : "${REVIEW_BUDGET:=1.0}" "${REVIEW_MAX_MIN:=240}";;
  full) : "${REVIEW_BUDGET:=1.8}" "${REVIEW_MAX_MIN:=360}";;
  *) echo "not a focus: $FOCUS (security, p2p, ui, full)"; exit 2;; esac
export REVIEW_FOCUS=$FOCUS REVIEW_BUDGET REVIEW_MAX_MIN
slug=$(printf '%s-%s-%s' "$(basename "$REPO" .git)" "${COMMIT:0:12}" "$FOCUS" | tr -c 'A-Za-z0-9._-' -)
# What the sandbox's user wrote belongs to a sub-uid here: removed inside
# podman's user namespace, as the agent's archive does (shrooms ADR-072).
RUN=/home/reviewer/runs/$slug; podman unshare rm -rf "$RUN"; mkdir -p "$RUN"/{src,checks,build,behaviour,media,logs}
DEST=/srv/reviews/$slug
# A review of the same commit again: the last one stays published beside it,
# named for when it ran. Overwriting in place left the earlier run's report
# showing on a run that never wrote one (forumer, 2026-10-27).
if [ -e "$DEST/index.html" ]; then mv "$DEST" "$DEST-$(date -u -r "$DEST/index.html" +%Y%m%d-%H%M)"; fi
rm -rf "$DEST"; mkdir -p "$DEST"
log(){ printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$RUN/logs/pipeline.log"; }
live(){ printf '%s\n' "$*" >> "$RUN/live.txt"; "$HERE/render.py" "$RUN" "$DEST" "$slug" live >/dev/null 2>&1 || true; }
inbox(){ podman run --rm --network "$1" -e REPO -e COMMIT -e LGX -v "$RUN:/run:z" -w /run "$IMG" bash -lc "$2"; }
export REPO COMMIT LGX

: > "$RUN/live.txt"; live "# Reviewing $REPO @ $COMMIT"; live "starting…"
log "review $REPO @ $COMMIT -> $RUN ; live at ${REVIEW_BASE:-https://or.vpavlin.xyz}/$slug/live.html"

live "## clone"; log "clone"
if [[ "$REPO" == localdir:* ]]; then
  cp -a "${REPO#localdir:}/." "$RUN/src/" 2>/dev/null; echo "localdir" > "$RUN/logs/commit"
else
inbox bridge 'git clone --quiet --filter=blob:none -- "$REPO" src 2>&1 | tail -3; cd src && git checkout --quiet "$COMMIT" -- 2>/dev/null; git rev-parse HEAD > /run/logs/commit 2>/dev/null; true'
fi
echo "$REPO" > "$RUN/logs/repo"
# The commit asked for, or nothing: a checkout that failed left the clone at
# its default branch, and a review of WhisperBox "@ 302a134…" started on
# main's 62a5336 instead (2026-10-29, a mistyped full hash).
# No clone at all is the network's fault, not the submission's: the queue
# tries the job again later (exit 75).
if [[ "$REPO" != localdir:* ]] && [ ! -s "$RUN/logs/commit" ]; then
  live "the clone failed (network?): will be tried again"; log "clone failed"; exit 75
fi
if [ "$COMMIT" != HEAD ] && [[ "$REPO" != localdir:* ]] && [[ "$(cat "$RUN/logs/commit" 2>/dev/null)" != "$COMMIT"* ]]; then
  live "the commit $COMMIT isn't in $REPO: stopped"; log "commit $COMMIT not found (clone is at $(cat "$RUN/logs/commit" 2>/dev/null))"; exit 2
fi

# The published package, if there is one: the reviewer installs this into
# Basecamp, so what is tested is what users install. (Its name is cleaned
# without the newline basename adds: tr made it ".lgx_", and no package was
# found; caught rebuilding the host on a VM, 2026-10-28.)
if [ -n "$LGX" ]; then
  live "## fetch the published packages"; log "lgx: $(echo $LGX)"
  mkdir -p "$RUN/lgx"
  # Each package, and its detached signature where the publisher gives one
  # (<package>.sig); names are cleaned with no newline, which tr made "_".
  for u in "${@:3}"; do
    [[ "$u" == localfile:* ]] || continue
    f=${u#localfile:}; cp "$INPUTS/$f" "$RUN/lgx/$f"; [ -f "$INPUTS/$f.sig" ] && cp "$INPUTS/$f.sig" "$RUN/lgx/$f.sig"
    live "  $f: from this host's inputs, not downloaded"
  done
  inbox bridge 'echo "$LGX" | while IFS= read -r u; do [ -n "$u" ] || continue; case $u in localfile:*) continue;; esac
      f=$(printf %s "${u##*/}" | tr -c "A-Za-z0-9._-" _)
      curl -sSfL --max-time 300 -o "lgx/$f" -- "$u" || echo "could not download $u" >&2
      curl -sfL --max-time 60 -o "lgx/$f.sig" -- "$u.sig" || rm -f "lgx/$f.sig"
    done; sha256sum lgx/*.lgx > logs/lgx.sha256 2>/dev/null; true' 2>&1 | while read -r e; do live "  $e"; done
  [ -s "$RUN/logs/lgx.sha256" ] && live "$(sed 's/^/  /' "$RUN/logs/lgx.sha256")"
  # What exactly is evaluated, each package: name, version, rootHash, its
  # signature and whose key made it, the official catalogue's view.
  : > "$RUN/logs/packages.jsonl"
  for l in "$RUN"/lgx/*.lgx; do
    [ -f "$l" ] || continue
    "$HERE/package.py" "$l" "$RUN/logs/package-$(basename "$l" .lgx).json" "$RUN/src" 2>&1 | while read -r d; do live "  package: $d"; done
    cat "$RUN/logs/package-$(basename "$l" .lgx).json" >> "$RUN/logs/packages.jsonl" 2>/dev/null; echo >> "$RUN/logs/packages.jsonl"
  done
  # What they need from the official catalogue, fetched here so the
  # sandbox's record of hosts contacted stays the module's own; what the
  # given packages provide themselves is not looked for there.
  given=$(for l in "$RUN"/lgx/*.lgx; do tar xzOf "$l" manifest.json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name",""))'; done | paste -sd,)
  for l in "$RUN"/lgx/*.lgx; do
    [ -f "$l" ] && "$HERE/fetch_deps.py" "$l" "$RUN/lgx/deps" "$HOME/lgx-cache" "$given" 2>&1 | while read -r d; do live "  dependency: $d"; done
  done
fi

live "## static checks (gitleaks, osv-scanner, semgrep)"; log "static"
# The scanners run on a copy without the repository's own scanner settings,
# and ignore its inline suppressions: a repository could otherwise switch
# off the checks on itself (FR-7). A scanner that fails says so.
inbox bridge 'cp -a src /tmp/scan && cd /tmp/scan
  find . \( -name .gitleaks.toml -o -name .gitleaksignore -o -name .semgrepignore -o -name osv-scanner.toml \) -print -delete > /run/checks/ignored-repo-config.txt
  gitleaks detect --no-banner --ignore-gitleaks-allow --report-format json --report-path /run/checks/gitleaks.json . >/dev/null 2>/run/checks/gitleaks.err; echo "gitleaks $?" >> /run/checks/exit-codes.txt
  osv-scanner --format json --recursive . > /run/checks/osv.json 2>/run/checks/osv.err; echo "osv-scanner $?" >> /run/checks/exit-codes.txt
  semgrep scan --quiet --json --disable-nosem --config auto . > /run/checks/semgrep.json 2>/run/checks/semgrep.err; echo "semgrep $?" >> /run/checks/exit-codes.txt
  true'
for c in gitleaks osv semgrep; do [ -s "$RUN/checks/$c.json" ] && live "  $c: $(wc -c < "$RUN/checks/$c.json") bytes"; done
# Exit codes that mean "it didn't run": gitleaks 1 and osv-scanner 1 mean
# findings, semgrep's 1 too; anything else, or no output, is a failure.
while read -r tool code; do
  case "$tool:$code" in *:0|gitleaks:1|osv-scanner:1|semgrep:1) ;; *) live "  $tool FAILED (exit $code): $(head -c 200 "$RUN/checks/${tool%-scanner}.err" 2>/dev/null)";; esac
done < "$RUN/checks/exit-codes.txt" 2>/dev/null
[ -s "$RUN/checks/ignored-repo-config.txt" ] && live "  the repository's own scanner settings were set aside: $(tr '\n' ' ' < "$RUN/checks/ignored-repo-config.txt")"

# Beside the review: the published packages rebuilt from this source with Nix,
# in a container of its own (rebuild.sh says why), and compared.
REBUILD=
if ls "$RUN"/lgx/*.lgx >/dev/null 2>&1; then
  mkdir -p "$RUN/rebuild"
  live "## rebuild the published packages from source with Nix (beside the review)"; log "rebuild"
  podman run --rm --name "rebuild-$slug-$$" --cap-add SYS_ADMIN --security-opt unmask=/proc/* --network bridge \
    -v "$RUN/src:/src:ro" -v "$RUN/lgx:/lgx:ro" -v "$RUN/rebuild:/out" -v "$HERE:/pipeline:ro" "$IMG" \
    bash /pipeline/rebuild.sh > "$RUN/logs/rebuild.txt" 2>&1 &
  REBUILD=$!
fi

# What the reviewer must cover, listed from the source before it starts.
echo "$FOCUS" > "$RUN/logs/focus"
if python3 "$HERE/inventory.py" "$RUN/src" "$FOCUS" > "$RUN/inventory.json" 2>"$RUN/logs/inventory.err"; then
  live "## focus: $FOCUS: $(jq -r '"\(.files) files and \(.methods) exposed methods, \(.lines) lines, to cover"' "$RUN/inventory.json"); budget $REVIEW_BUDGET DIEM, $REVIEW_MAX_MIN min"
else
  live "## focus: $FOCUS: the inventory failed ($(head -c 200 "$RUN/logs/inventory.err"))"; echo '{"items":[]}' > "$RUN/inventory.json"
fi
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

if [ -n "$REBUILD" ]; then
  wait "$REBUILD"
  live "  rebuild: $(tail -1 "$RUN/logs/rebuild.txt" 2>/dev/null)"
fi

log "publish"; "$HERE/render.py" "$RUN" "$DEST" "$slug" final 2>&1 | tee -a "$RUN/logs/pipeline.log"
# A copy on Logos Storage, where the host runs a node (host/50-storage.sh).
"$HERE/storage.py" "$DEST" 2>&1 | tee -a "$RUN/logs/pipeline.log" || true
"$HERE/index.py" /srv/reviews >/dev/null 2>&1 || log "the front page could not be updated"
log "done -> ${REVIEW_BASE:-https://or.vpavlin.xyz}/$slug/"
