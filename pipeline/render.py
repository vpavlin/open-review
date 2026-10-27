#!/usr/bin/env python3
# Render a finished run into a published review folder: a plain HTML index plus
# the raw evidence. Everything is escaped; no content from the module is ever
# served as HTML or script (the Caddyfile CSP is the second line).
import sys,os,json,html,glob,shutil
run,dest,slug=sys.argv[1:4]
os.makedirs(dest,exist_ok=True)
meta=json.load(open(os.path.join(run,"meta.json")))
def esc(x): return html.escape(str(x))
rows="".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k,v in meta["stages"].items())
# copy raw evidence verbatim (served as text/json, never html)
for sub in ("logs","checks","build","behaviour","media"):
    s=os.path.join(run,sub)
    if os.path.isdir(s): shutil.copytree(s,os.path.join(dest,sub),dirs_exist_ok=True)
for f in ("meta.json","chain.txt"):
    p=os.path.join(run,f)
    if os.path.exists(p): shutil.copy(p,dest)
body=f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>review: {esc(slug)}</title>
<style>body{{max-width:52em;margin:2em auto;padding:0 1em;font:16px/1.5 system-ui,sans-serif;background:#fbfbf8;color:#1d2125}}
table{{border-collapse:collapse}}td{{border:1px solid #ccc;padding:.3em .6em}}code{{background:#eef0ea;padding:0 .3em}}</style>
<h1>Review: {esc(slug)}</h1>
<p><b>Repository:</b> <code>{esc(meta['repo'])}</code> @ <code>{esc(meta['commit'])}</code><br>
<b>When:</b> {esc(meta['at'])} · <b>Model:</b> {esc(meta['model'])}<br>
<b>Sandbox:</b> {esc(meta['sandbox'])}</p>
<h2>Stages</h2><table>{rows}</table>
<h2>Evidence</h2><ul>
<li><a href="meta.json">meta.json</a> — inputs, file hashes</li>
<li><a href="chain.txt">chain.txt</a> — hash-chain root of the logs</li>
<li><a href="checks/">checks/</a> — gitleaks, osv-scanner, semgrep</li>
<li><a href="logs/">logs/</a> — the pipeline log</li>
<li><a href="behaviour/">behaviour/</a> — reads, writes, network, bait (dynamic stage)</li>
</ul>
<p style="color:#888">This is triage, not approval. The environment was instrumented; the sandbox is a container and its kernel version is the host's.</p>"""
open(os.path.join(dest,"index.html"),"w").write(body)
print("published:",dest)
