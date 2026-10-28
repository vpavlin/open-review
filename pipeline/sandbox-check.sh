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
asr() { runuser -u ondra -- "$@"; }   # as the reviewer
asm() { runuser -u pavel -- "$@"; }   # as the module
D=/run/behaviour/disguise.json
{
  check "the pipeline can't be changed from here" not touch /pipeline/.write-test
  check "Basecamp's AppImage can't be changed from here" not touch /opt/basecamp/Basecamp.AppImage
  check "no Venice key in the environment" not grep -qa VENICE_INFERENCE_KEY /proc/1/environ
  # A key-sized value, not the name: the pipeline's own code names it.
  check "no Venice key in reach on disk" not grep -rqsE 'VENICE_INFERENCE_KEY=[A-Za-z0-9_-]{16,}' /root /home/pavel /home/ondra /etc /run/logs /run/behaviour
  check "the review host's home isn't mounted" not test -e /home/reviewer
  check "cloud metadata unreachable" not curl -s -m 3 -o /dev/null http://169.254.169.254/
  check "the gateway refuses a request without the token" \
    test "$(curl -s -m 5 -o /dev/null -w '%{http_code}' -X POST "$GW/" -d '{}')" = 403
  check "no container marker at /run/.containerenv" not test -s /run/.containerenv
  check "no /.dockerenv" not test -e /.dockerenv
  check "hostname is the profile's" test "$(hostname)" = "$(jq -r .host "$D")"
  check "DMI says the profile's model" test "$(cat /sys/class/dmi/id/product_name 2>/dev/null)" = "$(jq -r .product "$D")"
  check "bait is planted" test -s /home/pavel/.ssh/id_ed25519
  # The reviewer runs as ondra, the module as pavel; root keeps the record.
  check "neither the reviewer nor the module is root" test "$(asr id -u)" != 0 -a "$(asm id -u)" != 0
  check "the reviewer can't become root" not asr sudo -n true
  check "the reviewer can run things as the module's user" test "$(asr as-module id -un)" = pavel
  check "the module can't use the reviewer's way in" not asm as-module true
  check "the module can't write the reviewer's report or probes" not asm touch /run/src/.write-test /run/probes/.write-test
  check "the module can't reach the reviewer's home" not asm ls /home/ondra
  check "the reviewer can't read the module's bait directly" not asr cat /home/pavel/.ssh/id_ed25519
  for who in asr asm; do
    check "$who: can't write the behaviour record" not $who touch /run/behaviour/.write-test
    check "$who: can't write the run's logs" not $who touch /run/logs/.write-test
    check "$who: can't change the firewall" not $who iptables -t nat -F OUTPUT
    check "$who: can't stop the proxies" not $who kill -0 "$(pgrep -o mitmdump)"
  done
  check "the module's web traffic goes to its proxy" \
    bash -c 'iptables -t nat -S OUTPUT | grep -q -- "--uid-owner 1000 .*--to-ports 8080"'
  check "the reviewer's web traffic goes to its own" \
    bash -c 'iptables -t nat -S OUTPUT | grep -q -- "--uid-owner 1001 .*--to-ports 8081"'
  # A request as each must come out decrypted in its own proxy's log.
  asm curl -s -m 15 -o /dev/null "https://example.com/?sandbox-check=m$$"
  asr curl -s -m 15 -o /dev/null "https://example.com/?sandbox-check=r$$"; sleep 1
  check "the module's HTTPS is decrypted and logged as the module's" grep -qF "sandbox-check=m$$" /run/behaviour/proxy.jsonl
  check "the reviewer's HTTPS is logged as the reviewer's" grep -qF "sandbox-check=r$$" /run/behaviour/proxy-reviewer.jsonl
} > "$OUT"
cat "$OUT"
exit $fail
