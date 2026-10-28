#!/usr/bin/env python3
# Tell a submitter how their review stands. Called by queue.py:
#
#   notify.py queued|started|done <job.json>
#
# How depends on where the submission came from (the job's notify field):
#   {"kind": "a2a", "to": "MACHINE/SESSION"}   an agent on the mesh: only the
#       result, as one A2A message (the queue position and the live link went
#       back in the reply that queued it; each A2A message is a task to the
#       receiver, so no more of them than that)
#   {"kind": "whisperbox", "form": ..., "confirmation": ...}   a private
#       reply to the WhisperBox answer, at each step (whisperbox.py)
import json, os, subprocess, sys

event, path = sys.argv[1], sys.argv[2]
job = json.load(open(path))
how = job.get("notify") or {}
kind = how.get("kind")


def text():
    if event == "queued":
        return f"Queued for review: {job['repo']} @ {job['commit'][:12]}. Live while it runs: {job['live']}"
    if event == "started":
        return f"Your review has started: {job['live']}"
    c = job.get("counts") or {}
    found = ", ".join(f"{v} {k}" for k, v in c.items() if v) or "no findings"
    return (f"Review done: {job['repo']} @ {job['commit'][:12]}: {job.get('result','')} ({found}"
            f"{', ' + job['cost'] if job.get('cost') else ''}). Report: {job['report']}")


try:
    if kind == "a2a" and event == "done":
        subprocess.run(["shrooms-agent", "a2a", "send", "--title", f"open-review: {job['slug']}",
                        how["to"], text()], timeout=60, capture_output=True)
    elif kind == "whisperbox":
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, "whisperbox.py"), "reply",
                        how["form"], how["confirmation"], text()], timeout=120, capture_output=True)
except Exception as e:
    print(f"notify: {e}", file=sys.stderr)
