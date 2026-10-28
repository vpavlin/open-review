#!/usr/bin/env python3
# as-module <command…>: run something as pavel, the user the module runs as,
# in the laptop session the disguise set up. The reviewer (ondra) runs
# untrusted things this way: the module's build and scripts, Basecamp with
# the module in it, probes linked against its code. What runs as pavel can't
# write the reviewer's report or probes, and its traffic is recorded as the
# module's. The root side is module_broker.py.
import json, os, socket, sys
if len(sys.argv) < 2:
    print("usage: as-module <command…>", file=sys.stderr); sys.exit(2)
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.connect("/run/desk/module.sock")
except OSError as e:
    print(f"as-module: no broker ({e})", file=sys.stderr); sys.exit(126)
socket.send_fds(s, [json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}).encode()], [0, 1, 2])
buf = b""
while not buf.endswith(b"\n"):
    b = s.recv(4096)
    if not b:
        sys.exit(125)
    buf += b
sys.exit(json.loads(buf).get("status", 125))
