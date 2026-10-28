#!/usr/bin/env python3
# The packages a module declares it needs, from the official Logos catalogue,
# as a user's Basecamp would fetch them on install. Runs on the host, not in
# the sandbox: these downloads are ours, and in the sandbox they would show up
# in the module's own record of hosts contacted.
#
#   fetch_deps.py <module.lgx> <out-dir> <cache-dir>
#
# Each download is checked against the index's sha256 and kept in the cache
# under that hash, so delivery_module's 98 MB comes once, not every review.
import hashlib, json, os, re, shutil, sys, tarfile, urllib.request

REPO = "https://raw.githubusercontent.com/logos-co/logos-modules-release/refs/heads/main/logos-repo.json"

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()

def ver(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

def satisfies(v, spec):
    # "~1.2.3" is >=1.2.3 within 1.2.x; "^1.2.3" within 1.x; a bare version is exact.
    spec = spec.strip()
    if not spec or spec == "*":
        return True
    op, want = (spec[0], spec[1:]) if spec[0] in "~^" else ("=", spec)
    a, b = ver(v), ver(want)
    if op == "~":
        return a[:2] == b[:2] and a >= b
    if op == "^":
        # npm's caret: ^1.2.3 <2.0.0, ^0.2.3 <0.3.0, ^0.0.3 only 0.0.3 (FR-11).
        if b[0] > 0: return a[:1] == b[:1] and a >= b
        if b[1] > 0: return a[:2] == b[:2] and a >= b
        return a == b
    return a == b

lgx, out, cache = sys.argv[1:4]
os.makedirs(out, exist_ok=True); os.makedirs(cache, exist_ok=True)
with tarfile.open(lgx) as t:
    manifest = json.load(t.extractfile("manifest.json"))
deps = manifest.get("dependencies", [])
if not deps:
    print("no dependencies"); sys.exit(0)
index = json.loads(get(json.loads(get(REPO))["indexUrl"]))
pk = index["packages"]
for d in deps:
    name, spec = d["name"], d.get("version", "")
    entry = pk.get(name) if isinstance(pk, dict) else next((p for p in pk if p.get("name") == name), None)
    vs = [v for v in (entry or {}).get("versions", []) if satisfies(v["manifest"]["version"], spec)]
    if not vs:
        print(f"{name} {spec}: not in the official catalogue"); continue
    v = max(vs, key=lambda v: ver(v["manifest"]["version"]))
    path = os.path.join(cache, v["sha256"] + ".lgx")
    if not os.path.exists(path):
        data = get(v["url"])
        if hashlib.sha256(data).hexdigest() != v["sha256"]:
            print(f"{name}: sha256 mismatch from {v['url']}, not used"); continue
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    shutil.copy(path, os.path.join(out, f"{name}-{v['manifest']['version']}.lgx"))
    print(f"{name} {v['manifest']['version']} (wanted {spec}) sha256 {v['sha256'][:16]}… rootHash {v.get('rootHash','')[:16]}…")
