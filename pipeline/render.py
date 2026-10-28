#!/usr/bin/env python3
# Render a run into the published folder. Two modes:
#   live   while a review runs: live.html meta-refreshes and shows the running
#          transcript (from the gateway's live.txt), escaped, no scripts.
#   final  when done: index.html (the report + evidence), and live.html stops
#          refreshing and points at it.
# Everything from the module is escaped; nothing is served as HTML or script.
import sys,os,json,html,glob,shutil,time,stat
run,dest,slug=sys.argv[1:4]; mode=sys.argv[4] if len(sys.argv)>4 else "final"
os.makedirs(dest,exist_ok=True)
def esc(x): return html.escape(str(x))
# Everything under the run dir was written, or could have been, by the module
# under review, and this runs on the host, where the Venice key is. So a
# file is opened one path component at a time, none of them a symlink, and
# only if it is a regular file: a symlink in media/ pointing at the key's
# file would otherwise be copied into the public review (open-review's own
# review, FR-1, 2026-10-28). Walking with dir_fd also leaves no window to
# swap a directory for a link while the module is still running.
RUNFD=os.open(run,os.O_RDONLY|os.O_DIRECTORY)
def open_beneath(rel,mode="rb"):
    parts=[x for x in os.path.normpath(rel).split(os.sep) if x not in ("",".")]
    if not parts or ".." in parts: raise PermissionError(rel)
    fd=os.dup(RUNFD)
    try:
        for d in parts[:-1]:
            nfd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd); os.close(fd); fd=nfd
        ffd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    finally: os.close(fd)
    if not stat.S_ISREG(os.fstat(ffd).st_mode): os.close(ffd); raise PermissionError(rel)
    return os.fdopen(ffd,mode) if "b" in mode else os.fdopen(ffd,mode,encoding="utf-8",errors="replace")
def exists_beneath(rel):
    try: open_beneath(rel).close(); return True
    except Exception: return False
def copy_beneath(rel,to):
    """Copy one regular file from the run dir; anything else is skipped."""
    try:
        with open_beneath(rel) as src, open(to,"wb") as out: shutil.copyfileobj(src,out,1<<20)
        return True
    except Exception: return False
def files_beneath(sub):
    """Regular files under run/sub, relative to run; links are not followed."""
    out=[]
    for root,dirs,files in os.walk(os.path.join(run,sub),followlinks=False):
        for f in files:
            out.append(os.path.relpath(os.path.join(root,f),run))
    return sorted(out)
def readf(p,n=200000):
    try:
        with open_beneath(p,"r") as f: return f.read()[-n:]
    except Exception: return ""
def readjson(p):
    try:
        with open_beneath(p,"r") as f: return json.load(f)
    except Exception: return None
CSS="body{max-width:60em;margin:1.5em auto;padding:0 1em;font:15px/1.5 system-ui,sans-serif;background:#0d0f12;color:#d8dde3}a{color:#6cf}h1,h2{color:#9fe}pre{white-space:pre-wrap;word-break:break-word;background:#15181d;padding:.8em;border-radius:6px;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #333;padding:.3em .6em}.sev{font-weight:bold}.red{color:#f66}"
def write(name,body): open(os.path.join(dest,name),"w").write(body)
MODEL=(readf(os.path.join("logs","model")).strip() or "venice/deepseek-v4-1-flash-uncensored")
FAILED=readf(os.path.join("logs","failed.txt")).strip()
# Venice's prices per million tokens (in, cached in, out), in DIEM = USD, 2026-10-28.
PRICES={"deepseek-v4-1-flash-uncensored":(0.33,0.00825,1.32),
        "deepseek-v4-1-flash-1017":(0.30,0.0075,1.20),"deepseek-v4-1-flash":(0.30,0.0075,1.20)}
def usage_stats(run):
    import glob
    calls=0; pin=0; pout=0; cached=0; ms=0; errors=0; retries=0
    if exists_beneath("gateway.jsonl"):
        for line in open_beneath("gateway.jsonl","r"):
            try: r=json.loads(line)
            except: continue
            if "retry_in_s" in r: retries+=1; continue
            calls+=1; ms+=r.get("ms",0)
            if r.get("status",200)>=400: errors+=1
            u=(r.get("response") or {}).get("usage") or {}
            pin+=u.get("prompt_tokens",0); pout+=u.get("completion_tokens",0)
            cached+=(u.get("prompt_tokens_details") or {}).get("cached_tokens",0)
    pi_,pc,po=PRICES.get(MODEL.split("/")[-1],(0.33,0.00825,1.32))
    cost=((pin-cached)*pi_ + cached*pc + pout*po)/1e6
    return {"model_calls":calls,"input_tokens":pin,"cached_input_tokens":cached,"output_tokens":pout,
            "model_seconds":round(ms/1000,1),"est_cost_usd":round(cost,4),
            "provider_errors":errors,"retries":retries,
            # Before 03aff47 streamed replies weren't logged, so no tokens either.
            "recorded":not (calls>errors and pin==0)}

if mode=="live":
    def latest_shot():
        shots=[x for x in files_beneath("media") if x.endswith(".png")]
        if not shots: return ""
        os.makedirs(os.path.join(dest,"media"),exist_ok=True)
        f=os.path.basename(shots[-1])
        if not copy_beneath(shots[-1],os.path.join(dest,"media",f)): return ""
        return f"<p><b>latest screen:</b> {esc(f[3:-4])}<br><img src='media/{esc(f)}' style='max-width:100%;border:1px solid #333'></p>"
    def last_line(path):
        # gateway.jsonl carries the whole conversation in every request and
        # runs to tens of MB; the status needs only its last line.
        try:
            with open_beneath(path) as f:
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
        calls=0; ctx=""
        if exists_beneath("gateway.jsonl"):
            with open_beneath("gateway.jsonl") as f: calls=sum(1 for _ in f)
            try:
                r=(json.loads(last_line("gateway.jsonl")).get("response") or {})
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
    copy_beneath("live.txt",os.path.join(dest,"live.txt"))
    write("live.html", f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=3>
<meta name=viewport content='width=device-width,initial-scale=1'><title>reviewing {esc(slug)}…</title>
<style>{CSS}</style><h1>Reviewing {esc(slug)}</h1>
<p style='color:#fa0'>● live — refreshes every 3 s; newest first · <a href="live.txt">full log</a></p>
{status()}{latest_shot()}<h2>Latest steps</h2>{shown}""")
    sys.exit(0)

# final: copy raw evidence (served as text/json, never html)
for sub in ("logs","checks","build","behaviour","media"):
    for rel in files_beneath(sub):
        to=os.path.join(dest,rel); os.makedirs(os.path.dirname(to),exist_ok=True)
        copy_beneath(rel,to)
for f in ("report.md","live.txt","session.log","gateway.jsonl","report.json"):
    copy_beneath(f,os.path.join(dest,f))
# hash-chain + meta
import hashlib
def h(rel):
    try:
        d=hashlib.sha256()
        with open_beneath(rel) as f:
            for b in iter(lambda: f.read(1<<20), b""): d.update(b)
        return d.hexdigest()
    except Exception: return ""
prev=""
for rel in files_beneath("."):
    v=h(rel)
    if v: prev=hashlib.sha256((prev+v).encode()).hexdigest()
write("chain.txt",prev+"\n")
def media_html():
    # What was copied into the published folder: regular files only.
    md=os.path.join(dest,"media"); out=[]
    if os.path.isfile(os.path.join(md,"session.mp4")):
        out.append("<video controls preload=metadata src='media/session.mp4' style='max-width:100%'></video>"
                   "<p style='color:#888'>The whole session in Basecamp, recorded in the sandbox.</p>")
    for f in sorted(glob.glob(os.path.join(md,"*.png"))):
        b=os.path.basename(f); cap=b[3:-4].replace("-"," ") if b[:2].isdigit() else b[:-4]
        out.append(f"<figure><img src='media/{esc(b)}' style='max-width:100%;border:1px solid #333'><figcaption>{esc(cap)}</figcaption></figure>")
    note=os.path.join(md,"GUI-did-not-run.txt")
    if os.path.isfile(note): out.append("<pre>"+esc(open(note,errors="replace").read()[:4000])+"</pre>")
    return ("<h2>Screenshots and recording</h2>"+"".join(out)) if out else ""
def failed_html():
    return ("<div style='border:2px solid #f66;padding:.6em 1em;border-radius:6px'>"
            "<h2 class=red style='margin-top:0'>Review failed</h2>"
            "<p>This is <b>not a verdict on the module</b>, good or bad: the review was not completed.</p>"
            f"<pre>{esc(FAILED)}</pre></div>")
rep=None
# Written in the sandbox: any shape at all. Not an object, it is no report
# (a malformed one stopped publication: FR-9).
rep=readjson("report.json")
if not isinstance(rep,dict): rep=None
beh={}
beh=readjson(os.path.join("behaviour","summary.json"))
if not isinstance(beh,dict): beh={}
repo=readf("logs/repo").strip(); commit=readf("logs/commit").strip()
# findings table (richer schema)
fr=""
def _list(v): return v if isinstance(v,list) else []
if rep:
    for f in _list(rep.get("findings"))[:200]:
        if not isinstance(f,dict): continue
        cl=" red" if str(f.get("severity","")).lower() in ("critical","high") else ""
        conf=esc(f.get("confirmed",""))
        fr+=(f"<tr><td>{esc(f.get('id',''))}</td><td class='sev{cl}'>{esc(f.get('severity',''))}</td>"
             f"<td>{esc(f.get('title',''))}</td><td>{conf}</td><td><code>{esc(f.get('files',f.get('file','')))}</code></td></tr>")
findings=(f"<table><tr><th>id</th><th>severity</th><th>finding</th><th>confirmed</th><th>where</th></tr>{fr}</table>"
          "<p>Full exploit and fix per finding in <a href='report.md'>report.md</a>.</p>") if fr else "<p>See <a href='report.md'>report.md</a>.</p>"
U=usage_stats(run)
def spend_by_activity():
    """Where the model budget went: each call's cost, put under what the call
    went on to run. This is what tells which part of a review to cut."""
    import re as _re
    cats={"reading the code":0.0,"builds and probes":0.0,"Basecamp (desk)":0.0,"writing the report":0.0,"other":0.0}
    if not exists_beneath("gateway.jsonl"): return ""
    for line in open_beneath("gateway.jsonl","r"):
        try: r=json.loads(line)
        except Exception: continue
        if "retry_in_s" in r or "budget_refused" in r: continue
        rj=r.get("response") or {}
        c=r.get("cost")
        if c is None:
            u=rj.get("usage") or {}; pin=u.get("prompt_tokens",0) or 0
            cached=(u.get("prompt_tokens_details") or {}).get("cached_tokens",0) or 0
            pi_,pc,po=PRICES.get(MODEL.split("/")[-1],(0.33,0.00825,1.32))
            c=((pin-cached)*pi_+cached*pc+(u.get("completion_tokens",0) or 0)*po)/1e6
        cmd=" ".join(t["function"].get("arguments","") for t in ((rj.get("choices") or [{}])[0].get("message",{}).get("tool_calls") or []))
        if r.get("phase")=="report" or _re.search(r"report\.(md|json)",cmd): k="writing the report"
        elif _re.search(r"\bdesk\b",cmd): k="Basecamp (desk)"
        elif _re.search(r"g\+\+|clang|cmake|ninja|\bmake\b|/run/probes|\./p_|probe|node -e|npm ",cmd): k="builds and probes"
        elif _re.search(r"\bgrep\b|sed -n|\bcat\b|\bhead\b|\bfind\b|\bls\b|\bwc\b|\brg\b",cmd) or not cmd: k="reading the code"
        else: k="other"
        cats[k]+=c
    tot=sum(cats.values()) or 1
    rows="".join(f"<tr><td>{esc(k)}</td><td>{v:.3f}</td><td>{100*v/tot:.0f}%</td></tr>" for k,v in cats.items() if v>0.0005)
    return f"<table><tr><th>went on</th><th>DIEM</th><th></th></tr>{rows}</table>"
def budget_line():
    d=readjson(os.path.join("logs","spend.json"))
    if not isinstance(d,dict): return "no cap for this run"
    hit=[ph for ph in ("testing","report") if exists_beneath(os.path.join("logs",f"budget-spent-{ph}.txt"))]
    return (f"{d['spent']:.3f} of {d['budget']:.2f} DIEM ({d['testing']:.2f} for testing)"
            + (f"; the {' and '.join(hit)} share ran out" if hit else ""))
def charged():
    """What Venice actually took: the account's balance before the review
    minus after it. Whole account, so other use in the same window counts."""
    a=readjson(os.path.join("logs","balance-start.json")); b=readjson(os.path.join("logs","balance-end.json"))
    if not (isinstance(a,dict) and isinstance(b,dict)): return "not recorded for this run"
    if "error" in a or "error" in b: return "not recorded: "+esc(a.get("error") or b.get("error"))
    ne=a.get("next_epoch") or ""
    try:
        from datetime import datetime
        if ne and datetime.fromisoformat(ne.replace("Z","+00:00")).timestamp() <= b["t"]:
            return "not measurable: the daily DIEM allowance refilled during the run"
    except Exception: pass
    parts=[]
    for cur in ("DIEM","USD"):
        d=(a["balances"].get(cur) or 0)-(b["balances"].get(cur) or 0)
        if abs(d)>=0.00005: parts.append(f"{d:.4f} {cur}")
    return (" + ".join(parts) or "0") + " <span style='color:#888'>(the Venice account's balance before minus after; any other use of the account in that time counts too)</span>"
usage=(f"<table><tr><th>model calls</th><td>{U['model_calls']}</td></tr>"
       f"<tr><th>input tokens</th><td>{U['input_tokens']:,} ({U['cached_input_tokens']:,} cached)</td></tr>"
       f"<tr><th>output tokens</th><td>{U['output_tokens']:,}</td></tr>"
       f"<tr><th>model time</th><td>{U['model_seconds']} s</td></tr>"
       f"<tr><th>charged by Venice</th><td>{charged()}</td></tr>"
       f"<tr><th>computed</th><td>${U['est_cost_usd']} <span style='color:#888'>(this review's tokens × Venice's list price for {esc(MODEL)})</span></td></tr>"
       f"<tr><th>budget</th><td>{budget_line()}</td></tr>"
       f"<tr><th>provider errors</th><td>{U['provider_errors']} (retries {U['retries']})</td></tr></table>"
       f"{spend_by_activity()}")
if not U["recorded"]:
    usage=(f"<p>{U['model_calls']} model calls, {U['model_seconds']} s of model time. Token counts were not "
           "recorded for this run: the gateway didn't log streamed replies yet.</p>")
ran="".join(f"<li>{esc(x)}</li>" for x in _list(rep.get("ran"))[:30]) if rep else ""
nottested="".join(f"<li>{esc(x)}</li>" for x in _list(rep.get("not_tested"))[:30]) if rep else ""
behrow=""
if beh.get("bait_files_read"): behrow+=f"<li class='red'>read bait: {esc(', '.join(beh['bait_files_read']))}</li>"
if beh.get("contacted_hosts"): behrow+=f"<li>contacted: {esc(', '.join(beh['contacted_hosts']))}</li>"
for x in (beh.get("bait_sent_out") or [])[:20]:
    if isinstance(x,dict): behrow+=f"<li class='red'><b>sent bait out:</b> {esc(x.get('bait',''))} → {esc(x.get('to',''))}</li>"
if beh.get("read_secret_then_contacted_external_host") and not beh.get("bait_sent_out"): behrow+="<li class='red'>read a secret, then contacted an external host</li>"
reqs=[x for x in (beh.get("http_requests") or []) if isinstance(x,str)]
if reqs: behrow+=f"<li>HTTP(S) requests, recorded by the proxy ({len(reqs)}): <ul>"+"".join(f"<li><code>{esc(x)}</code></li>" for x in reqs[:40])+("<li>… the rest in behaviour/proxy.jsonl</li>" if len(reqs)>40 else "")+"</ul></li>"
if beh.get("tls_refused_by_client"): behrow+=f"<li>refused the recording proxy's certificate (pins or brings its own trust): {esc(', '.join(beh['tls_refused_by_client']))}</li>"
if beh.get("connected_addresses"): behrow+=f"<li>connected to {len(beh['connected_addresses'])} address(es): {esc(', '.join(beh['connected_addresses'][:15]))}</li>"
write("live.html", f"""<!doctype html><meta charset=utf-8><title>{esc(slug)} — done</title><style>{CSS}</style>
<h1>{esc(slug)}</h1><p>Review finished. <a href="index.html">Read the report →</a></p>""")
write("index.html", f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>review: {esc(slug)}</title><style>{CSS}</style>
<h1>Review: {esc(slug)}</h1>
<p><b>Repository:</b> <code>{esc(repo)}</code> @ <code>{esc(commit)}</code><br>
<b>When:</b> {esc(time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime()))} · <b>Model:</b> {esc(MODEL)}<br>
<b>Sandbox:</b> container dressed as a laptop; the host kernel is not hidden.
{('<br><b class=red>'+esc(readf(os.path.join('logs','timed-out.txt')))+'</b>') if exists_beneath(os.path.join('logs','timed-out.txt')) else ''}
{('<br><b style="color:#fa0">'+esc(readf(os.path.join('logs','written-after.txt')))+'</b>') if exists_beneath(os.path.join('logs','written-after.txt')) else ''}
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
