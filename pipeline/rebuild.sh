#!/usr/bin/env bash
# Rebuild the published packages from the reviewed source, and compare.
# Run by review.sh in a container of its own, beside the review: /src the
# repository (read-only), /lgx the published packages (read-only), /out where
# the verdict goes (rebuild.json, logs, the rebuilt packages).
#
# Nix builds inside its own sandbox, as the published ones were built: our
# first rebuild of LNS without it embedded /nix/var/nix/builds/nix-15-…/ where
# the release has /build/, and differed only in that (2026-10-29). The sandbox
# needs SYS_ADMIN and an unmasked /proc, which the review's sandbox doesn't
# give (an unmasked /proc shows the host's processes): hence a container of
# its own, with no disguise, no secrets and no model. Builds run as pavel.
set -u
# Root's, not the module user's: the review's sandbox sees this folder
# (/run/rebuild), and its module must not be able to write the verdict.
OUT=/out; mkdir -p "$OUT/built" "$OUT/logs"; chmod 755 "$OUT" "$OUT/built" "$OUT/logs"
W=/home/pavel/src
cp -a /src "$W" && chown -R pavel:pavel "$W"

# Which published package is which: name -> file.
declare -A PUB
for l in /lgx/*.lgx; do
  [ -f "$l" ] || continue
  n=$(tar xzOf "$l" manifest.json 2>/dev/null | jq -r .name); [ -n "$n" ] && PUB[$n]=$l
done
# The module flakes in the repository, by the name in their metadata.json:
# a flake that takes another as an input (names_ui takes names) is built
# against the copy here, as the author's release script does.
declare -A LOCAL
for f in $(find "$W" -maxdepth 3 -name flake.nix -not -path '*/node_modules/*' | sort); do
  d=$(dirname "$f"); n=$(jq -r '.name // empty' "$d/metadata.json" 2>/dev/null)
  [ -n "$n" ] && LOCAL[$n]=$d
done

for n in "${!LOCAL[@]}"; do
  d=${LOCAL[$n]}
  [ -n "${PUB[$n]:-}" ] || continue               # only what was published
  over=()
  for i in $(jq -r '.nodes.root.inputs // {} | keys[]' "$d/flake.lock" 2>/dev/null); do
    [ -n "${LOCAL[$i]:-}" ] && [ "${LOCAL[$i]}" != "$d" ] && over+=(--override-input "$i" "path:${LOCAL[$i]}")
  done
  s=$(date +%s)
  su pavel -c "cd '$d' && timeout 45m nix build --option sandbox true --option sandbox-fallback false \
      '.#lgx-portable' ${over[*]:-} -o '$d/result-lgx'" > "$OUT/logs/$n.log" 2>&1
  rc=$?
  echo "$n: nix build exit $rc in $(( $(date +%s) - s )) s" >> "$OUT/logs/summary.txt"
  b=$(ls "$d"/result-lgx/*.lgx 2>/dev/null | head -1)
  [ -n "$b" ] && cp "$b" "$OUT/built/$n.lgx"
done

# The verdict, per published package.
python3 - "$OUT" <<'PY'
import json, os, subprocess, sys, tarfile
out = sys.argv[1]; res = {}
for f in sorted(os.listdir("/lgx")):
    if not f.endswith(".lgx"): continue
    try:
        m = json.load(tarfile.open(f"/lgx/{f}").extractfile("manifest.json"))
    except Exception:
        continue
    n = m.get("name"); built = f"{out}/built/{n}.lgx"
    r = {"published": f, "version": m.get("version")}
    if not os.path.isfile(built):
        r["verdict"] = "not built"
        log = f"{out}/logs/{n}.log"
        r["why"] = (open(log, errors="replace").read()[-600:] if os.path.isfile(log)
                    else "no flake in the repository names this package")
    else:
        c = subprocess.run(["bash", "/pipeline/lgx-compare.sh", f"/lgx/{f}", built], capture_output=True, text=True)
        r["compare"] = c.stdout.strip().splitlines()
        same = [l for l in r["compare"] if l.startswith("SAME     variants/")]
        diff = [l for l in r["compare"] if l.startswith("DIFFERS")]
        r["verdict"] = "identical" if same and not diff else ("differs" if diff else "nothing to compare")
    res[n] = r
json.dump(res, open(f"{out}/rebuild.json", "w"), indent=1)
print(json.dumps({k: v["verdict"] for k, v in res.items()}))
PY
chmod -R a+rX "$OUT"
