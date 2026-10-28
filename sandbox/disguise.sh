#!/usr/bin/env bash
# Make the sandbox look like an ordinary Linux laptop, not a container, so a
# submitted module that goes quiet when it detects analysis has a harder time.
# This is a standard anti-evasion measure for a defensive reviewer; every
# review states plainly that the environment was instrumented. It is tied to
# this reviewer and never shipped as a general "defeat any sandbox" tool.
#
# Run once at the start of a review, as root inside the cage. It does the parts
# that are reliable in a rootless podman cage and skips the rest with a note;
# what it could not do is recorded so the report can say so.
set -uo pipefail
PROFILES=${1:-/usr/local/sbin/profiles.json}
OUT=${2:-/tmp/disguise.json}
key=$(python3 -c "import json,random;print(random.choice(list(json.load(open('$PROFILES')))))" 2>/dev/null || echo xps13-9340)
IFS='|' read vendor product cpu mem res host <<<"$(python3 -c "import json;p=json.load(open('$PROFILES'))['$key'];print('|'.join([p['vendor'],p['product'],p['cpu'],str(p['mem_gb']),p['res'],p['host']]))")"
did=(); skip=()

# Hostname and the container markers that can be removed from inside.
hostname "$host" 2>/dev/null && did+=("hostname=$host") || skip+=("hostname")
: > /tmp/.empty 2>/dev/null
for f in /.dockerenv /run/.containerenv; do
  [ -e "$f" ] || continue
  if rm -f "$f" 2>/dev/null; then did+=("rm $f")
  elif mount --bind /tmp/.empty "$f" 2>/dev/null; then did+=("masked $f")
  else skip+=("$f"); fi
done

# A lived-in look for the user's home.
h=/root
mkdir -p "$h/Documents" "$h/Downloads" "$h/.mozilla/firefox/ab12cd.default-release" "$h/.config"
: > "$h/.bash_history"; printf '%s\n' "cd ~/Documents" "ls" "firefox" "code ." "git status" "sudo apt update" >> "$h/.bash_history"
printf 'invoices-2026.ods\nnotes.md\ntax-return.pdf\n' > "$h/Documents/.listing" 2>/dev/null
did+=("home dressed")

# DMI/vendor strings live in read-only sysfs; faking them needs a bind mount
# over /sys/class/dmi/id, which a rootless cage usually cannot do. Try, note if not.
if command -v mount >/dev/null && [ -w /tmp ]; then
  d=/tmp/.dmi; mkdir -p "$d"
  printf '%s' "$vendor"  > "$d/sys_vendor"
  printf '%s' "$product" > "$d/product_name"
  if mount --bind "$d/sys_vendor" /sys/class/dmi/id/sys_vendor 2>/dev/null \
     && mount --bind "$d/product_name" /sys/class/dmi/id/product_name 2>/dev/null; then
    did+=("dmi=$vendor/$product")
  else
    skip+=("dmi (needs host bind-mounts / CAP_SYS_ADMIN)")
  fi
else
  skip+=("dmi")
fi

# Environment for child processes (the module and the GUI it runs in).
cat > /tmp/disguise.env <<ENV
XDG_SESSION_TYPE=wayland
XDG_CURRENT_DESKTOP=GNOME
DESKTOP_SESSION=gnome
LANG=en_US.UTF-8
HOSTNAME=$host
ENV
did+=("env written to /tmp/disguise.env")

printf '%s\n' "${did[@]}" > /tmp/disguise.did; printf '%s\n' "${skip[@]}" > /tmp/disguise.skip
python3 - "$OUT" "$key" "$vendor" "$product" "$cpu" "$mem" "$res" <<PY
import json,sys
json.dump({"profile":sys.argv[2],"vendor":sys.argv[3],"product":sys.argv[4],"cpu":sys.argv[5],
           "mem_gb":int(sys.argv[6]),"resolution":sys.argv[7],
           "host":"$host",
           "applied":[l for l in open("/tmp/disguise.did").read().splitlines() if l],
           "not_applied":[l for l in open("/tmp/disguise.skip").read().splitlines() if l],
           "note":"container disguise; the kernel version is the host's and cannot be hidden"},
          open(sys.argv[1],"w"),indent=1)
PY
echo "disguise: profile $key; applied ${#did[@]}, skipped ${#skip[@]} (see $OUT)"
