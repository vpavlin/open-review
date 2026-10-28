#!/usr/bin/env python3
# The Venice account's balance now, for the cost a review really ran up:
# read before and after it, the difference is what was charged. The
# per-request ledger needs an admin key, which has no place on a box that
# runs hostile code; this needs only the inference key.
#
#   balance.py <out.json>        (VENICE_INFERENCE_KEY in the environment)
import json, os, sys, time, urllib.request
r = urllib.request.Request("https://api.venice.ai/api/v1/api_keys/rate_limits",
                           headers={"Authorization": "Bearer " + os.environ["VENICE_INFERENCE_KEY"]})
try:
    d = json.load(urllib.request.urlopen(r, timeout=30))["data"]
    out = {"t": int(time.time()), "balances": d.get("balances", {}), "next_epoch": d.get("nextEpochBegins")}
except Exception as e:
    out = {"t": int(time.time()), "error": str(e)}
json.dump(out, open(sys.argv[1], "w"))
