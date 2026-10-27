#!/usr/bin/env python3
# Render a run into the published folder. Two modes:
#   live   while a review runs: live.html meta-refreshes and shows the running
#          transcript (from the gateway's live.txt), escaped, no scripts.
#   final  when done: index.html (the report + evidence), and live.html stops
#          refreshing and points at it.
# Everything from the module is escaped; nothing is served as HTML or script.
import sys,os,json,html,glob,shutil,time
run,dest,slug=sys.argv[1:4]; mode=sys.argv[4] if len(sys.argv)>4 else "final"
os.makedirs(dest,exist_ok=True)
def esc(x): return html.escape(str(x))
def readf(p,n=200000):
    try: return open(os.path.join(run,p),encoding="utf-8",errors="replace").read()[-n:]
    except: return ""
CSS="body{max-width:60em;margin:1.5em auto;padding:0 1em;font:15px/1.5 system-ui,sans-serif;background:#0d0f12;color:#d8dde3}a{color:#6cf}h1,h2{color:#9fe}pre{white-space:pre-wrap;word-break:break-word;background:#15181d;padding:.8em;border-radius:6px;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #333;padding:.3em .6em}.sev{font-weight:bold}.red{color:#f66}"
def write(name,body): open(os.path.join(dest,name),"w").write(body)

if mode=="live":
    t=readf("live.txt")
    write("live.html", f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=3>
<meta name=viewport content='width=device-width,initial-scale=1'><title>reviewing {esc(slug)}…</title>
<style>{CSS}</style><h1>Reviewing {esc(slug)}</h1>
<p style='color:#fa0'>● live — this page refreshes every 3s</p><pre>{esc(t)}</pre>""")
    sys.exit(0)

# final: copy raw evidence (served as text/json, never html)
for sub in ("logs","checks","build","behaviour","media"):
    s=os.path.join(run,sub)
    if os.path.isdir(s): shutil.copytree(s,os.path.join(dest,sub),dirs_exist_ok=True)
for f in ("report.md","live.txt","session.log","gateway.jsonl"):
    p=os.path.join(run,f)
    if os.path.exists(p): shutil.copy(p,dest)
# hash-chain + meta
import hashlib
def h(p):
    try: return hashlib.sha256(open(p,'rb').read()).hexdigest()
    except: return ""
prev=""
for p in sorted(glob.glob(run+'/**/*',recursive=True)):
    if os.path.isfile(p): prev=hashlib.sha256((prev+h(p)).encode()).hexdigest()
write("chain.txt",prev+"\n")
rep=None
try: rep=json.load(open(os.path.join(run,"report.json")))
except: pass
shutil.copy(os.path.join(run,"report.json"),dest) if os.path.exists(os.path.join(run,"report.json")) else None
beh={}
try: beh=json.load(open(os.path.join(run,"behaviour","summary.json")))
except: pass
repo=readf("logs/repo").strip(); commit=readf("logs/commit").strip()
# findings table
fr=""
if rep and rep.get("findings"):
    for f in rep["findings"]:
        cl=" red" if str(f.get("severity","")).lower() in ("critical","high") else ""
        fr+=f"<tr><td class='sev{cl}'>{esc(f.get('severity',''))}</td><td>{esc(f.get('title',''))}</td><td>{esc(f.get('evidence',''))}</td><td><code>{esc(f.get('file',''))}</code></td></tr>"
findings=f"<table><tr><th>severity</th><th>finding</th><th>evidence</th><th>where</th></tr>{fr}</table>" if fr else "<p>No structured findings parsed; see report.md.</p>"
behrow=""
if beh.get("bait_files_read"): behrow+=f"<li class='red'>read bait: {esc(', '.join(beh['bait_files_read']))}</li>"
if beh.get("contacted_hosts"): behrow+=f"<li>contacted: {esc(', '.join(beh['contacted_hosts']))}</li>"
if beh.get("read_secret_then_contacted_external_host"): behrow+="<li class='red'>read a secret, then contacted an external host</li>"
write("live.html", f"""<!doctype html><meta charset=utf-8><title>{esc(slug)} — done</title><style>{CSS}</style>
<h1>{esc(slug)}</h1><p>Review finished. <a href="index.html">Read the report →</a></p>""")
write("index.html", f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>review: {esc(slug)}</title><style>{CSS}</style>
<h1>Review: {esc(slug)}</h1>
<p><b>Repository:</b> <code>{esc(repo)}</code> @ <code>{esc(commit)}</code><br>
<b>When:</b> {esc(time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime()))} · <b>Model:</b> venice/deepseek-v4-1-flash-uncensored<br>
<b>Sandbox:</b> container dressed as a laptop; the host kernel is not hidden.
{'<br><b class=red>The repository contained text addressed to the reviewer.</b>' if rep and rep.get('repo_tried_to_instruct_reviewer') else ''}</p>
<p><b>Summary:</b> {esc(rep.get('verdict_summary','(see report.md)')) if rep else '(see report.md)'}</p>
<h2>Findings</h2>{findings}
<h2>Observed behaviour</h2><ul>{behrow or '<li>nothing flagged</li>'}</ul>
<h2>Evidence</h2><ul>
<li><a href="report.md">report.md</a> — the reviewer's full writeup</li>
<li><a href="report.json">report.json</a> · <a href="chain.txt">chain.txt</a> (hash-chain root)</li>
<li><a href="session.log">session.log</a> — the reviewer's session · <a href="gateway.jsonl">gateway.jsonl</a> — every model call</li>
<li><a href="behaviour/">behaviour/</a> (strace, dns, bait) · <a href="checks/">checks/</a> (gitleaks, osv, semgrep) · <a href="media/">media/</a></li>
<li><a href="live.txt">live.txt</a> — the running transcript</li></ul>
<p style='color:#888'>Triage, not approval. Automated and imperfect; the environment was instrumented.</p>""")
print("published:",dest)
