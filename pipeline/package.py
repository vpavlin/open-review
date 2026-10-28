#!/usr/bin/env python3
# What exactly was evaluated: the published package's identity, for the
# report's headline ("evaluated forumer 0.2.5, rootHash …") and for the
# Basecamp module security plan's Freeze rule and Evaluated Releases catalog,
# which want a review tied to one rootHash. Runs on the host after the .lgx
# is fetched; writes logs/package.json.
#
#   package.py <module.lgx> <out.json> [<repository checkout>]
#
# A .lgx carries no signature of its own (2026-10-28: forumer, delivery_module
# and whisperbox_core have none). A publisher may sign it beside it
# (<package>.sig, an SSH signature, as LNS does): that is checked, and the key
# that made it is looked for among the public keys in the repository at the
# reviewed commit. And a catalogue may vouch for it: this says whether the
# official Logos catalogue lists this version, with the same rootHash.
import base64, glob, hashlib, json, os, struct, subprocess, sys, tarfile, tempfile, urllib.request


def sshsig(sig_path, data_path, repo):
    """A detached SSH signature: valid or not, the key that made it, and
    which public key in the repository it is, if any."""
    try:
        b64 = "".join(l for l in open(sig_path).read().splitlines() if not l.startswith("-----"))
        blob = base64.b64decode(b64)
        if blob[:6] != b"SSHSIG":
            return {"kind": "unknown"}
        def strings(b, i):
            n = struct.unpack(">I", b[i:i + 4])[0]; return b[i + 4:i + 4 + n], i + 4 + n
        _, i = None, 10                            # magic + version
        pub, i = strings(blob, i)
        ns, i = strings(blob, i)
        ns = ns.decode()
        out = subprocess.run(["ssh-keygen", "-Y", "check-novalidate", "-n", ns, "-s", sig_path],
                             stdin=open(data_path, "rb"), capture_output=True, text=True, timeout=30)
        ok = out.returncode == 0
        fp = out.stdout.strip().rsplit(" ", 1)[-1] if ok else ""
        rec = {"kind": "ssh", "namespace": ns, "valid": ok, "key": fp}
        # Which public key in the repository at this commit made it.
        for k in glob.glob(os.path.join(repo or "/nonexistent", "**", "*.pub"), recursive=True)[:200]:
            f = subprocess.run(["ssh-keygen", "-lf", k], capture_output=True, text=True, timeout=10).stdout.split()
            if len(f) > 1 and f[1] == fp:
                rec["key_in_repository"] = os.path.relpath(k, repo); break
        return rec
    except Exception as e:
        return {"kind": "error", "error": str(e)[:200]}

REPO = "https://raw.githubusercontent.com/logos-co/logos-modules-release/refs/heads/main/logos-repo.json"
lgx, out = sys.argv[1:3]
repo = sys.argv[3] if len(sys.argv) > 3 else None
sha = hashlib.sha256(open(lgx, "rb").read()).hexdigest()
with tarfile.open(lgx) as t:
    m = json.load(t.extractfile("manifest.json"))
    files = t.getnames()
rec = {"file": lgx.rsplit("/", 1)[-1], "sha256": sha, "name": m.get("name"), "version": m.get("version"),
       "type": m.get("type"), "rootHash": (m.get("hashes") or {}).get("root"), "hashes": m.get("hashes"),
       "author": m.get("author") or "", "dependencies": m.get("dependencies", []),
       "variants": sorted({f.split("/")[1] for f in files if f.startswith("variants/") and f.count("/") >= 2}),
       "signed": any(f.endswith((".sig", ".sign", "signature.json")) for f in files)}
if os.path.isfile(lgx + ".sig"):
    rec["signature"] = sshsig(lgx + ".sig", lgx, repo)
    rec["signed"] = bool(rec["signature"].get("valid"))
try:
    catalog = json.load(urllib.request.urlopen(REPO, timeout=60))
    index = json.load(urllib.request.urlopen(catalog["indexUrl"], timeout=60))
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
sig = rec.get("signature") or {}
print(f"{rec['name']} {rec['version']}: rootHash {str(rec['rootHash'])[:16]}…, sha256 {sha[:16]}…, "
      f"signature: {('good, key '+sig.get('key','')+(' = '+sig['key_in_repository'] if sig.get('key_in_repository') else ' (not in the repository)')) if sig.get('valid') else (sig.get('kind') and 'BAD' or 'none')}, "
      f"official catalogue: {rec['official']}")
