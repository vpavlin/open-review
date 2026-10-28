#!/usr/bin/env bash
# The sandbox checks itself before the reviewer starts, and the review does
# not start if a check fails (after agentic-job's probes: a restriction that
# is assumed is not one). Run inside the sandbox by review-in-sandbox.sh,
# after the disguise and before pi.
#
#   sandbox-check.sh <gateway-url> <out.txt>
# Exit 0 if everything holds; the results, pass or fail, go to <out.txt>.
GW=$1; OUT=$2; fail=0
check() {  # check "<what must hold>" <command that succeeds when it holds>
  local what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=1; fi
}
not() { ! "$@"; }
asu() { runuser -u pavel -- "$@"; }   # as the user the reviewer and the module run as
D=/run/behaviour/disguise.json
{
  check "the pipeline can't be changed from here" not touch /pipeline/.write-test
  check "Basecamp's AppImage can't be changed from here" not touch /opt/basecamp/Basecamp.AppImage
  check "no Venice key in the environment" not grep -qa VENICE_INFERENCE_KEY /proc/1/environ
  # A key-sized value, not the name: the pipeline's own code names it.
  check "no Venice key in reach on disk" not grep -rqsE 'VENICE_INFERENCE_KEY=[A-Za-z0-9_-]{16,}' /root /home/pavel /etc /run/logs /run/behaviour
  check "the review host's home isn't mounted" not test -e /home/reviewer
  check "cloud metadata unreachable" not curl -s -m 3 -o /dev/null http://169.254.169.254/
  check "the gateway refuses a request without the token" \
    test "$(curl -s -m 5 -o /dev/null -w '%{http_code}' -X POST "$GW/" -d '{}')" = 403
  check "no container marker at /run/.containerenv" not test -s /run/.containerenv
  check "no /.dockerenv" not test -e /.dockerenv
  check "hostname is the profile's" test "$(hostname)" = "$(jq -r .host "$D")"
  check "DMI says the profile's model" test "$(cat /sys/class/dmi/id/product_name 2>/dev/null)" = "$(jq -r .product "$D")"
  check "bait is planted" test -s /home/pavel/.ssh/id_ed25519
  # The reviewer and the module run as pavel, who must not reach the record.
  check "the reviewer is not root" test "$(asu id -u)" != 0
  check "the reviewer can't use sudo" not asu sudo -n true
  check "the reviewer can't write the behaviour record" not asu touch /run/behaviour/.write-test
  check "the reviewer can't write the run's logs" not asu touch /run/logs/.write-test
  check "the reviewer can't change the firewall" not asu iptables -t nat -F OUTPUT
  check "the reviewer can't stop the proxy" not asu kill -0 "$(pgrep -o mitmdump)"
  check "the reviewer's web traffic is redirected to the proxy" \
    bash -c 'iptables -t nat -S OUTPUT | grep -q -- "--uid-owner 1000 .*--to-ports 8080"'
  # A request as the user must come out in the proxy's log, decrypted.
  probe="https://example.com/?sandbox-check=$$"
  asu curl -s -m 15 -o /dev/null "$probe"; sleep 1
  check "the reviewer's HTTPS is decrypted and logged" grep -qF "sandbox-check=$$" /run/behaviour/proxy.jsonl
} > "$OUT"
cat "$OUT"
exit $fail
