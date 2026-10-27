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
MODEL=(readf(os.path.join("logs","model")).strip() or "venice/deepseek-v4-1-flash-uncensored")
FAILED=readf(os.path.join("logs","failed.txt")).strip()
def usage_stats(run):
    import glob
    p=os.path.join(run,"gateway.jsonl")
    calls=0; pin=0; pout=0; cached=0; ms=0; errors=0; retries=0
    if os.path.exists(p):
        for line in open(p,encoding="utf-8",errors="replace"):
            try: r=json.loads(line)
            except: continue
            if "retry_in_s" in r: retries+=1; continue
            calls+=1; ms+=r.get("ms",0)
            if r.get("status",200)>=400: errors+=1
            u=(r.get("response") or {}).get("usage") or {}
            pin+=u.get("prompt_tokens",0); pout+=u.get("completion_tokens",0)
            cached+=(u.get("prompt_tokens_details") or {}).get("cached_tokens",0)
    # Venice's prices per million tokens (in, cached in, out), 2026-10-27.
    prices={"deepseek-v4-1-flash-uncensored":(0.33,0.00825,1.32),
            "deepseek-v4-1-flash-1017":(0.30,0.0075,1.20),"deepseek-v4-1-flash":(0.30,0.0075,1.20)}
    pi_,pc,po=prices.get(MODEL.split("/")[-1],(0.33,0.00825,1.32))
    cost=((pin-cached)*pi_ + cached*pc + pout*po)/1e6
    return {"model_calls":calls,"input_tokens":pin,"cached_input_tokens":cached,"output_tokens":pout,
            "model_seconds":round(ms/1000,1),"est_cost_usd":round(cost,4),
            "provider_errors":errors,"retries":retries,
            # Before 03aff47 streamed replies weren't logged, so no tokens either.
            "recorded":not (calls>errors and pin==0)}

if mode=="live":
    def latest_shot():
        shots=sorted(glob.glob(os.path.join(run,"media","*.png")))
        if not shots: return ""
        os.makedirs(os.path.join(dest,"media"),exist_ok=True)
        f=os.path.basename(shots[-1]); shutil.copy(shots[-1],os.path.join(dest,"media",f))
        return f"<p><b>latest screen:</b> {esc(f[3:-4])}<br><img src='media/{esc(f)}' style='max-width:100%;border:1px solid #333'></p>"
    def last_line(path):
        # gateway.jsonl carries the whole conversation in every request and
        # runs to tens of MB; the status needs only its last line.
        try:
            with open(path,"rb") as f:
                f.seek(0,2); end=f.tell(); step=1<<16; pos=end; buf=b""
                while pos>0:
                    pos=max(0,pos-step); f.seek(pos); buf=f.read(end-pos)
                    if buf.rstrip(b"\n").count(b"\n")>=1: break
                return buf.rstrip(b"\n").split(b"\n")[-1].decode("utf-8","replace")
        except Exception: return ""
    def status():
        pl=readf(os.path.join("logs","pipeline.log")).strip().splitlines()
        started=pl[0][:8] if pl else ""
        stages=[l[9:].split()[0] if l[9:].startswith("lgx ") else l[9:] for l in pl if not l[9:].startswith("review ")]
        gw=os.path.join(run,"gateway.jsonl"); calls=0; ctx=""
        if os.path.exists(gw):
            with open(gw,"rb") as f: calls=sum(1 for _ in f)
            try:
                r=(json.loads(last_line(gw)).get("response") or {})
                ctx=f" · context {((r.get('usage') or {}).get('prompt_tokens') or 0):,} tokens"
            except Exception: pass
        return (f"<p>started {esc(started)} UTC · now {time.strftime('%H:%M:%S',time.gmtime())} UTC · "
                f"{calls} model calls{ctx} · model {esc(MODEL)}</p>"
                f"<p style='color:#888'>stages: {esc(' → '.join(stages))}</p>")
    # The newest few steps, newest first: the page refreshes every 3 s and
    # lands at the top, where a full log put the latest step at the far end.
    t=readf("live.txt")
    steps=[x for x in t.split("\n▶ ") if x.strip()]
    shown="".join(f"<pre>{esc(('▶ ' if i or len(steps)>1 else '')+x.strip()[:2500])}</pre>"
                  for i,x in enumerate(reversed(steps[-6:])))
    try: shutil.copy(os.path.join(run,"live.txt"),os.path.join(dest,"live.txt"))
    except Exception: pass
    write("live.html", f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=3>
<meta name=viewport content='width=device-width,initial-scale=1'><title>reviewing {esc(slug)}…</title>
<style>{CSS}</style><h1>Reviewing {esc(slug)}</h1>
<p style='color:#fa0'>● live — refreshes every 3 s; newest first · <a href="live.txt">full log</a></p>
{status()}{latest_shot()}<h2>Latest steps</h2>{shown}""")
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
def media_html():
    md=os.path.join(run,"media"); out=[]
    if os.path.exists(os.path.join(md,"session.mp4")):
        out.append("<video controls preload=metadata src='media/session.mp4' style='max-width:100%'></video>"
                   "<p style='color:#888'>The whole session in Basecamp, recorded in the sandbox.</p>")
    for f in sorted(glob.glob(os.path.join(md,"*.png"))):
        b=os.path.basename(f); cap=b[3:-4].replace("-"," ") if b[:2].isdigit() else b[:-4]
        out.append(f"<figure><img src='media/{esc(b)}' style='max-width:100%;border:1px solid #333'><figcaption>{esc(cap)}</figcaption></figure>")
    note=os.path.join(md,"GUI-did-not-run.txt")
    if os.path.exists(note): out.append("<pre>"+esc(open(note).read())+"</pre>")
    return ("<h2>Screenshots and recording</h2>"+"".join(out)) if out else ""
def failed_html():
    return ("<div style='border:2px solid #f66;padding:.6em 1em;border-radius:6px'>"
            "<h2 class=red style='margin-top:0'>Review failed</h2>"
            "<p>This is <b>not a verdict on the module</b>, good or bad: the review was not completed.</p>"
            f"<pre>{esc(FAILED)}</pre></div>")
rep=None
try: rep=json.load(open(os.path.join(run,"report.json")))
except: pass
shutil.copy(os.path.join(run,"report.json"),dest) if os.path.exists(os.path.join(run,"report.json")) else None
beh={}
try: beh=json.load(open(os.path.join(run,"behaviour","summary.json")))
except: pass
repo=readf("logs/repo").strip(); commit=readf("logs/commit").strip()
# findings table (richer schema)
fr=""
if rep and rep.get("findings"):
    for f in rep["findings"]:
        cl=" red" if str(f.get("severity","")).lower() in ("critical","high") else ""
        conf=esc(f.get("confirmed",""))
        fr+=(f"<tr><td>{esc(f.get('id',''))}</td><td class='sev{cl}'>{esc(f.get('severity',''))}</td>"
             f"<td>{esc(f.get('title',''))}</td><td>{conf}</td><td><code>{esc(f.get('files',f.get('file','')))}</code></td></tr>")
findings=(f"<table><tr><th>id</th><th>severity</th><th>finding</th><th>confirmed</th><th>where</th></tr>{fr}</table>"
          "<p>Full exploit and fix per finding in <a href='report.md'>report.md</a>.</p>") if fr else "<p>See <a href='report.md'>report.md</a>.</p>"
U=usage_stats(run)
usage=(f"<table><tr><th>model calls</th><td>{U['model_calls']}</td></tr>"
       f"<tr><th>input tokens</th><td>{U['input_tokens']:,} ({U['cached_input_tokens']:,} cached)</td></tr>"
       f"<tr><th>output tokens</th><td>{U['output_tokens']:,}</td></tr>"
       f"<tr><th>model time</th><td>{U['model_seconds']} s</td></tr>"
       f"<tr><th>estimated cost</th><td>${U['est_cost_usd']}</td></tr>"
       f"<tr><th>provider errors</th><td>{U['provider_errors']} (retries {U['retries']})</td></tr></table>")
if not U["recorded"]:
    usage=(f"<p>{U['model_calls']} model calls, {U['model_seconds']} s of model time. Token counts were not "
           "recorded for this run: the gateway didn't log streamed replies yet.</p>")
ran="".join(f"<li>{esc(x)}</li>" for x in (rep.get("ran") or [])[:30]) if rep else ""
nottested="".join(f"<li>{esc(x)}</li>" for x in (rep.get("not_tested") or [])[:30]) if rep else ""
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
<b>When:</b> {esc(time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime()))} · <b>Model:</b> {esc(MODEL)}<br>
<b>Sandbox:</b> container dressed as a laptop; the host kernel is not hidden.
{('<br><b class=red>'+esc(readf(os.path.join('logs','timed-out.txt')))+'</b>') if os.path.exists(os.path.join(run,'logs','timed-out.txt')) else ''}
{'<br><b class=red>The repository contained text addressed to the reviewer.</b>' if rep and rep.get('repo_tried_to_instruct_reviewer') else ''}</p>
{failed_html() if FAILED else f"<p><b>Summary:</b> {esc(rep.get('verdict_summary','(see report.md)')) if rep else '(see report.md)'}</p><h2>Findings</h2>{findings}"}
{media_html()}
<h2>Usage</h2>{usage}
{ran and ('<h2>What was run</h2><ul>'+ran+'</ul>')}
{nottested and ('<h2>Not tested</h2><ul>'+nottested+'</ul>')}
<h2>Observed behaviour{' (partial: the review did not finish)' if FAILED else ''}</h2><ul>{behrow or ('<li>nothing recorded before it stopped</li>' if FAILED else '<li>nothing flagged</li>')}</ul>
<h2>Evidence</h2><ul>
<li><a href="report.md">report.md</a> — the reviewer's full writeup</li>
<li><a href="report.json">report.json</a> · <a href="chain.txt">chain.txt</a> (hash-chain root)</li>
<li><a href="session.log">session.log</a> — the reviewer's session · <a href="gateway.jsonl">gateway.jsonl</a> — every model call</li>
<li><a href="behaviour/">behaviour/</a> (strace, dns, bait) · <a href="checks/">checks/</a> (gitleaks, osv, semgrep) · <a href="media/">media/</a></li>
<li><a href="live.txt">live.txt</a> — the running transcript</li></ul>
<p style='color:#888'>Triage, not approval. Automated and imperfect; the environment was instrumented.</p>""")
print("published:",dest)
