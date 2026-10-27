#!/usr/bin/env bash
# Record what a command does: every file it opens (and fails to open), the
# processes it starts, and the connections it makes, across the whole process
# tree. Writes a log the reviewer and the pipeline read.
#
#   record.sh <logdir> -- <command...>
#
# Writes outside the module's own folder, and the network capture, are done on
# the host side (an overlay diff and a logging netns); this is the in-cage part.
set -uo pipefail
log=${1:?logdir}; shift; [ "${1:-}" = -- ] && shift
mkdir -p "$log"
strace -f -qq -e trace=openat,open,connect,execve,unlink,unlinkat,rename \
       -e signal=none -s 200 -o "$log/strace.log" "$@"
rc=$?
grep -oE 'openat?\([^)]*"([^"]+)"[^)]*' "$log/strace.log" 2>/dev/null | grep -oE '"[^"]+"' | tr -d '"' | sort -u > "$log/files.txt" || true
grep -E 'connect\(' "$log/strace.log" 2>/dev/null | grep -oE 'inet_addr\("[^"]+"\)|sin6_addr[^,]*|htons\([0-9]+\)' | sort -u > "$log/connects.txt" || true
grep -E 'execve\(' "$log/strace.log" 2>/dev/null | grep -oE 'execve\("[^"]+"' | sort -u > "$log/exec.txt" || true
echo "record: rc=$rc; see $log/{strace.log,files.txt,connects.txt,exec.txt}"
exit $rc
