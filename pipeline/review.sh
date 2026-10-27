#!/usr/bin/env bash
# Review one Basecamp module. Runs on the review host as the reviewer user
# (needs podman to launch the sandbox). One task = one review (open-review PoC).
#
#   review.sh <repo-url> [<commit>] [<lgx-url>]
#
# Stages, each writing into the run dir:
#   clone    the repo at a commit, inside a throwaway container
#   static   semgrep, gitleaks, osv-scanner over the source
#   build    build the module and compare with the submitted .lgx
#   dynamic  install and drive it in the disguised sandbox, recording all of it   [being built]
#   report   the pi reviewer writes report.md / report.json from the evidence      [being built]
#   publish  hash-chain the logs, render HTML, copy to /srv/reviews/<slug>/
set -uo pipefail
IMG=localhost/open-reviewer:latest
REPO=${1:?repo url}; COMMIT=${2:-HEAD}; LGX=${3:-}
slug=$(printf '%s-%s' "$(basename "$REPO" .git)" "${COMMIT:0:12}" | tr -c 'A-Za-z0-9._-' -)
RUN=/home/reviewer/runs/$slug; rm -rf "$RUN"; mkdir -p "$RUN"/{src,checks,build,behaviour,media,logs}
log(){ printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$RUN/logs/pipeline.log"; }
inbox(){ podman run --rm --network "$1" -v "$RUN:/run:z" -w /run "$IMG" bash -lc "$2"; }

log "review $REPO @ $COMMIT  ->  $RUN"

# --- clone: a throwaway container, network only for the fetch ---
log "clone"
inbox bridge "git clone --quiet --filter=blob:none '$REPO' src && cd src && git checkout --quiet '$COMMIT' 2>/dev/null || true; git -C src rev-parse HEAD > /run/logs/commit 2>/dev/null; true" \
  || { log "clone failed"; }
echo "$REPO" > "$RUN/logs/repo"

# --- static: no network needed; secrets, deps, patterns ---
log "static"
inbox bridge 'cd src
  gitleaks detect --no-banner --report-format json --report-path /run/checks/gitleaks.json . >/dev/null 2>&1 || true
  osv-scanner --format json --recursive . > /run/checks/osv.json 2>/dev/null || true
  semgrep scan --quiet --json --config auto . > /run/checks/semgrep.json 2>/dev/null || true
  true'
for c in gitleaks osv semgrep; do [ -s "$RUN/checks/$c.json" ] && log "  $c: $(wc -c < "$RUN/checks/$c.json") bytes" || log "  $c: (empty)"; done

# --- build + compare (module build is per-ecosystem; recorded, best effort) ---
log "build"
inbox bridge 'cd src
  if [ -f flake.nix ]; then echo "nix flake present (build TODO)"; fi
  if [ -f metadata.json ]; then cp metadata.json /run/build/metadata.json; fi
  ls -la > /run/build/tree.txt
  true' >/dev/null 2>&1
[ -n "$LGX" ] && log "  submitted lgx: $LGX (compare TODO)"

# --- dynamic: being built ---
log "dynamic: being built (disguised sandbox drives Basecamp, records behaviour)"
echo '{"status":"not yet run","note":"dynamic stage being built"}' > "$RUN/behaviour/summary.json"

# --- report: being built (pi reviewer writes from the evidence) ---
log "report: being built"
python3 - "$RUN" "$REPO" "$COMMIT" <<'PY'
import json,sys,os,hashlib,glob,time
run,repo,commit=sys.argv[1:4]
def h(p):
  try: return hashlib.sha256(open(p,'rb').read()).hexdigest()
  except: return None
files={os.path.relpath(p,run):h(p) for p in glob.glob(run+'/**/*',recursive=True) if os.path.isfile(p)}
meta={"repo":repo,"commit":commit,"at":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      "sandbox":"container (disguised); host kernel not hidden","model":"venice/deepseek-v4-1-flash-uncensored",
      "stages":{"clone":"done","static":"done","build":"partial","dynamic":"being built","report":"being built"},
      "files_sha256":files}
json.dump(meta,open(run+'/meta.json','w'),indent=1)
# hash-chain the logs: each line's hash folds in the previous
import pathlib
prev=''
for p in sorted(glob.glob(run+'/logs/*'))+sorted(glob.glob(run+'/checks/*')):
  prev=hashlib.sha256((prev+h(p)).encode()).hexdigest()
open(run+'/chain.txt','w').write(prev+'\n')
print("meta + chain written; chain root",prev[:16])
PY

# --- publish ---
log "publish"
DEST=/srv/reviews/$slug
mkdir -p "$DEST"
python3 "$(dirname "$0")/render.py" "$RUN" "$DEST" "$slug" 2>&1 | tee -a "$RUN/logs/pipeline.log"
log "done -> http://77.237.236.27/$slug/"
