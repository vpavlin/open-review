#!/usr/bin/env python3
# What exactly was evaluated: the published package's identity, for the
# report's headline ("evaluated forumer 0.2.5, rootHash …") and for the
# Basecamp module security plan's Freeze rule and Evaluated Releases catalog,
# which want a review tied to one rootHash. Runs on the host after the .lgx
# is fetched; writes logs/package.json.
#
#   package.py <module.lgx> <out.json>
#
# A .lgx carries no signature of its own (2026-10-28: forumer, delivery_module
# and whisperbox_core have none); a catalogue vouches for it instead. So this
# says whether the official Logos catalogue lists this version, and with the
# same rootHash.
import hashlib, json, sys, tarfile, urllib.request

REPO = "https://raw.githubusercontent.com/logos-co/logos-modules-release/refs/heads/main/logos-repo.json"
lgx, out = sys.argv[1:3]
sha = hashlib.sha256(open(lgx, "rb").read()).hexdigest()
with tarfile.open(lgx) as t:
    m = json.load(t.extractfile("manifest.json"))
    files = t.getnames()
rec = {"file": lgx.rsplit("/", 1)[-1], "sha256": sha, "name": m.get("name"), "version": m.get("version"),
       "type": m.get("type"), "rootHash": (m.get("hashes") or {}).get("root"), "hashes": m.get("hashes"),
       "author": m.get("author") or "", "dependencies": m.get("dependencies", []),
       "variants": sorted({f.split("/")[1] for f in files if f.startswith("variants/") and f.count("/") >= 2}),
       "signed": any(f.endswith((".sig", ".sign", "signature.json")) for f in files)}
try:
    repo = json.load(urllib.request.urlopen(REPO, timeout=60))
    index = json.load(urllib.request.urlopen(repo["indexUrl"], timeout=60))
    pk = index.get("packages", [])
    entry = pk.get(rec["name"]) if isinstance(pk, dict) else next((p for p in pk if p.get("name") == rec["name"]), None)
    if not entry:
        rec["official"] = {"listed": False}
    else:
        same = [v for v in entry.get("versions", []) if (v.get("manifest") or {}).get("version") == rec["version"]]
        rec["official"] = {"listed": True, "version_listed": bool(same),
                           "rootHash_matches": bool(same) and same[0].get("rootHash") == rec["rootHash"],
                           "sha256_matches": bool(same) and same[0].get("sha256") == sha,
                           "versions": [(v.get("manifest") or {}).get("version") for v in entry.get("versions", [])][:10]}
except Exception as e:
    rec["official"] = {"error": str(e)[:200]}
json.dump(rec, open(out, "w"), indent=1)
print(f"{rec['name']} {rec['version']}: rootHash {str(rec['rootHash'])[:16]}…, sha256 {sha[:16]}…, "
      f"official catalogue: {rec['official']}")
