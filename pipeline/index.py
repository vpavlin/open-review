#!/usr/bin/env python3
# The front page: every published review, newest first, with its verdict,
# what it found and what it cost. A review of the same commit again keeps the
# earlier ones (published as <slug>-<time>); they are listed under it.
#
#   index.py [reviews dir, default /srv/reviews]
import html, json, os, re, sys, time
D = sys.argv[1] if len(sys.argv) > 1 else "/srv/reviews"
esc = lambda x: html.escape(str(x))
reviews = []
for name in sorted(os.listdir(D)):
    p = os.path.join(D, name)
    if not os.path.isdir(p) or os.path.islink(p) or not os.path.isfile(os.path.join(p, "index.html")):
        continue
    try:
        r = json.load(open(os.path.join(p, "review.json")))
    except Exception:  # published before review.json existed: from its report.json
        r = {"title": name, "pill": "see report", "verdict": "info", "counts": {}, "cost": "", "summary": "",
             "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(os.path.getmtime(os.path.join(p, "index.html"))))}
        if not os.path.isfile(os.path.join(p, "report.json")):
            r["verdict"], r["pill"] = "failed", "No report"
        try:
            rep = json.load(open(os.path.join(p, "report.json")))
            sev = ["critical", "high", "medium", "low"]
            fs = [f for f in rep.get("findings", []) if isinstance(f, dict)]
            r["counts"] = {v: sum(1 for f in fs if v in str(f.get("severity", "")).lower()) for v in sev}
            worst = next((v for v in sev if r["counts"][v]), "none")
            r["verdict"], r["pill"] = worst, worst.capitalize() if worst != "none" else "Nothing found"
            r["summary"] = rep.get("verdict_summary", "") if isinstance(rep.get("verdict_summary"), str) else ""
        except Exception:
            pass
    m = re.match(r"^(.*)-(\d{8}-\d{4}|run\d+)$", name)
    r["dir"], r["base"] = name, (m.group(1) if m else name)
    reviews.append(r)
latest = {}
for r in sorted(reviews, key=lambda r: r.get("when", "")):
    latest.setdefault(r["base"], []).append(r)
rows = []
for base, rs in sorted(latest.items(), key=lambda kv: kv[1][-1].get("when", ""), reverse=True):
    r = next((x for x in reversed(rs) if x["dir"] == base), rs[-1])
    earlier = [x for x in rs if x is not r]
    counts = r.get("counts") or {}
    chips = "".join(f"<span class='chip sev-{k}'>{v} {k}</span>" for k, v in counts.items() if v)
    summ = r.get("summary", "")
    summ = summ if len(summ) < 320 else summ[:319] + "…"
    rows.append(
        f"<a class=row href='{esc(r['dir'])}/'><div class=top><span class='verdict v-{esc(r.get('verdict','info'))}'>{esc(r.get('pill',''))}</span>"
        f"<b>{esc(r.get('title', base))}</b><span class=when>{esc(r.get('when',''))}</span></div>"
        f"<div class=sub><code>{esc(r.get('repo',''))}</code>{' @ <code>'+esc(str(r.get('commit',''))[:12])+'</code>' if r.get('commit') else ''}"
        f"{' · '+esc(r['cost']) if r.get('cost') else ''}"
        f"{' · Logos Storage <code>'+esc(r['storage']['cid'][:14])+'…</code>' if isinstance(r.get('storage'),dict) and r['storage'].get('cid') else ''}"
        f"</div><div class=chips>{chips}</div><p>{esc(summ)}</p></a>"
        + (f"<div class=earlier>earlier: " + " · ".join(f"<a href='{esc(x['dir'])}/'>{esc(x.get('when',''))} ({esc(x.get('pill',''))})</a>" for x in reversed(earlier)) + "</div>" if earlier else ""))
CSS = """
:root{--bg:#0b0d10;--panel:#14181d;--line:#232a32;--fg:#d9dee4;--dim:#8b95a1;--acc:#6cc8ff;
--critical:#ff4d5e;--high:#ff8a3d;--medium:#f5c542;--low:#7bc8a4;--info:#8b95a1;--none:#5fd38d;--failed:#ff4d5e}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:60em;margin:0 auto;padding:2em 1.2em 4em}a{color:var(--acc)}code{font-family:ui-monospace,Menlo,monospace;font-size:.86em}
h1{font-size:2em;margin:.2em 0}.lead{color:var(--dim);max-width:44em}
a.row{display:block;color:inherit;text-decoration:none;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1em 1.2em;margin-top:1em}
a.row:hover{border-color:#3a4652}.top{display:flex;gap:.7em;align-items:center;flex-wrap:wrap}.top b{font-size:1.15em}.when{margin-left:auto;color:var(--dim);font-size:.85em}
.sub{color:var(--dim);font-size:.88em;margin-top:.2em;overflow-wrap:anywhere}a.row p{margin:.5em 0 0;color:#b8c0c8;font-size:.92em}
.verdict{display:inline-block;padding:.15em .7em;border-radius:999px;font-weight:700;font-size:.8em;color:#0b0d10;background:var(--info)}
.v-critical{background:var(--critical)}.v-high{background:var(--high)}.v-medium{background:var(--medium)}.v-low{background:var(--low)}.v-none{background:var(--none)}.v-failed{background:var(--failed)}
.chips{margin-top:.4em}.chip{display:inline-block;margin:.1em .3em .1em 0;padding:0 .5em;border-radius:5px;border:1px solid var(--line);font-size:.8em}
.chip.sev-critical{color:var(--critical)}.chip.sev-high{color:var(--high)}.chip.sev-medium{color:var(--medium)}.chip.sev-low{color:var(--low)}
.earlier{color:var(--dim);font-size:.82em;margin:.3em .4em 0}footer{color:var(--dim);font-size:.85em;margin-top:2.5em}
"""
page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>open review</title><style>{CSS}</style><main>
<h1>open review</h1>
<p class=lead>Automatic, adversarial reviews of Logos Basecamp modules: each module is built, installed,
used and attacked in a sandbox dressed as a laptop, and everything it reads, runs and sends is recorded.
Triage, not approval. <a href="https://github.com/vpavlin/open-review">How it works</a>.</p>
{''.join(rows) or '<p>No reviews yet.</p>'}
<footer>{len(latest)} module(s), {len(reviews)} review(s). Proof of concept.</footer></main>"""
tmp = os.path.join(D, ".index.html.tmp")
open(tmp, "w").write(page)
os.replace(tmp, os.path.join(D, "index.html"))
print("index:", len(reviews), "reviews")
