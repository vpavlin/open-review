#!/bin/bash
# A stand-in for pi, for testing a host's setup without a model or a key
# (REVIEW_TEST_PI=this review.sh …): it does what a reviewer and a hostile
# module would, and the sandbox's record has to show it. Run on the leaky
# control (test-modules/leaky-build).
# Sent back by review-loop.sh (pi --continue): cover the rest of the
# inventory, so the loop's way through to "covered" is tested too.
if [ "${1:-}" = --continue ]; then
  { echo "continue: $(printf %s "${@: -1}" | head -1 | cut -c1-80)"
    python3 -c '
import json; inv=json.load(open("/run/inventory.json")); c={}
for i in inv["items"]:
    c[i["id"]]={"status":"checked","read":"1-%d"%max(i.get("lines",1),1),"note":"stand-in: marked by the fake reviewer, nothing read"}
json.dump(c,open("/run/src/coverage.json","w"))'
  } >> /run/probes/fake-pi.out 2>&1
  exit 0
fi
{
echo "reviewer is $(whoami)"
echo "inventory: $(python3 -c 'import json;d=json.load(open("/run/inventory.json"));print(d["focus"],len(d["items"]),"items")')"
echo '{}' > /run/src/coverage.json
cat /home/pavel/.ssh/id_ed25519 >/dev/null 2>&1 && echo "BAD: the reviewer read the bait" || echo "ok: the reviewer can't read the bait"
touch /run/behaviour/x 2>/dev/null && echo "BAD: wrote the record" || echo "ok: the record is out of reach"
printf '# draft\n' > /run/src/report.md
as-module bash -c 'echo pwned > /run/src/report.md 2>/dev/null && echo "BAD: the module wrote the report" || echo "ok: the module cannot write the report"; cd /run/src && node collect.js'
desk start | tail -1
desk shot desktop
cat > /run/src/report.md <<'R'
# leaky-build — stand-in review
## 1. Bottom line
A stand-in for the model ran; this tests the host, not the module.
R
echo '{"verdict_summary":"stand-in: tests the host setup","findings":[{"id":"FR-1","severity":"Critical","title":"stand-in finding","confirmed":"run"}]}' > /run/src/report.json
} >> /run/probes/fake-pi.out 2>&1
exit 0
