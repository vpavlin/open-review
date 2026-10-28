#!/usr/bin/env python3
# Mirror a published review to Logos Storage: the whole public folder as one
# .tar.gz, uploaded to the review host's own node (host/50-storage.sh), and
# its CID written beside the review (storage.json, review.json) for the page
# and the front page. Anyone on the logos.test network can fetch it by CID
# while a node holds it; ours does, and nothing pays for more.
#
#   storage.py <published review dir>
import hashlib, io, json, os, sys, tarfile, time, urllib.request

import html as _html
API = os.environ.get("LOGOS_STORAGE_API", "http://127.0.0.1:8099/api/storage/v1")


def storage_html(rec):
    """The page's line about the Logos Storage copy (render.py uses it too)."""
    e = lambda x: _html.escape(str(x))
    return (f"<section><h2>Logos Storage</h2><p>This review, every file of it, as one archive: "
            f"<code>{e(rec['cid'])}</code> on {e(rec['network'])} ({rec['bytes']:,} bytes, sha256 "
            f"<code>{e(rec['sha256'][:16])}…</code>). Any Logos Storage node on that network can fetch it "
            f"by its CID while one holds it: the review host's node does; nothing pays for more.</p></section>")


def main():
  dest = os.path.abspath(sys.argv[1])
  name = os.path.basename(dest)

  try:
      urllib.request.urlopen(API + "/debug/info", timeout=5).read()
  except Exception as e:
      sys.exit(f"storage: no node at {API} ({e})")

  buf = io.BytesIO()
  with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as t:
      for root, dirs, files in os.walk(dest):
          for f in sorted(files):
              p = os.path.join(root, f)
              if f in ("storage.json",) or os.path.islink(p):
                  continue
              t.add(p, arcname=os.path.join(name, os.path.relpath(p, dest)), recursive=False)
  data = buf.getvalue()
  req = urllib.request.Request(API + "/data", data=data, method="POST", headers={
      # The node refuses application/gzip ("not a valid MIME type").
      "Content-Type": "application/octet-stream",
      "Content-Disposition": f'attachment; filename="{name}.tar.gz"'})
  cid = urllib.request.urlopen(req, timeout=600).read().decode().strip()
  chain = ""
  try:
      chain = open(os.path.join(dest, "chain.txt")).read().strip()
  except OSError:
      pass
  rec = {"cid": cid, "network": "logos.test", "file": f"{name}.tar.gz", "bytes": len(data),
         "sha256": hashlib.sha256(data).hexdigest(), "chain": chain,
         "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
  json.dump(rec, open(os.path.join(dest, "storage.json"), "w"), indent=1)
  try:
      rj = os.path.join(dest, "review.json")
      r = json.load(open(rj)); r["storage"] = rec; json.dump(r, open(rj, "w"))
  except Exception:
      pass
  print(f"storage: {cid} ({len(data)} bytes)")
  try:
    ip = os.path.join(dest, "index.html")
    page = open(ip).read()
    if "<!--storage-->" in page:
      open(ip, "w").write(page.replace("<!--storage-->", storage_html(rec), 1))
  except OSError:
    pass


if __name__ == "__main__":
  main()
