#!/usr/bin/env python3
# Render a run into the published folder. Two modes:
#   live   while a review runs: live.html meta-refreshes and shows the running
#          transcript (from the gateway's live.txt), escaped, no scripts.
#   final  when done: index.html (the report + evidence), and live.html stops
#          refreshing and points at it.
# Everything from the module is escaped; nothing is served as HTML or script.
import sys,os,json,html,glob,shutil,time,stat,re
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
# Only evidence of the kinds we produce is published, all of it served as
# text, JSON or media: whatever else the module left in these folders stays
# here (FR-16). Caddy types files by extension.
PUBLISH=(".png",".mp4",".txt",".log",".json",".jsonl",".err",".out",".mitm")
for sub in ("logs","checks","build","behaviour","media","rebuild"):
    for rel in files_beneath(sub):
        if not rel.lower().endswith(PUBLISH): continue
        to=os.path.join(dest,rel); os.makedirs(os.path.dirname(to),exist_ok=True)
        copy_beneath(rel,to)
for f in ("report.md","live.txt","session.log","gateway.jsonl","report.json","inventory.json","coverage.json"):
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
def _short(x,n=150): return x if len(x)<=n else x[:n-1]+"…"
if reqs: behrow+=(f"<li><details><summary>HTTP(S) requests, recorded by the proxy ({len(reqs)})</summary><ul>"
                  +"".join(f"<li><code>{esc(_short(x))}</code></li>" for x in reqs[:60])
                  +("<li>… the rest in behaviour/proxy.jsonl</li>" if len(reqs)>60 else "")+"</ul></details></li>")
if beh.get("tls_refused_by_client"): behrow+=f"<li>refused the recording proxy's certificate (pins or brings its own trust): {esc(', '.join(beh['tls_refused_by_client']))}</li>"
if beh.get("connected_addresses"): behrow+=f"<li>connected to {len(beh['connected_addresses'])} address(es): {esc(', '.join(beh['connected_addresses'][:15]))}</li>"
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import mdsafe
md=readf("report.md",2_000_000)
sec=mdsafe.sections(md)
def section(*names):
    """A report section by its heading's start, e.g. "1. Bottom line"."""
    for k,v in sec.items():
        if any(k.lower().startswith(n.lower()) or k.lower().split(". ",1)[-1].startswith(n.lower()) for n in names): return v
    return ""
SEV=["critical","high","medium","low"]
def sevof(x):
    x=str(x).lower()
    return next((v for v in SEV if v in x),"info")
flist=[f for f in _list(rep.get("findings"))[:200] if isinstance(f,dict)] if rep else []
counts={v:sum(1 for f in flist if sevof(f.get("severity",""))==v) for v in SEV}
worst=next((v for v in SEV if counts[v]),"none")
if FAILED: worst="failed"
pill={"critical":"Critical","high":"High","medium":"Medium","low":"Low","none":"Nothing found","failed":"Review failed"}[worst]
# The finding's own section of report.md, with its exploit and fix.
def finding_body(f):
    fid=str(f.get("id","")).strip()
    for k,v in sec.items():
        if fid and k.startswith(fid+" ") or k.startswith(fid+"—") or k.startswith(fid+" —"): return mdsafe.render(v,shift=2)
    parts=[]
    for key,label in (("exploit","Exploit"),("fix","Fix")):
        if f.get(key): parts.append(f"<p><b>{label}:</b> {esc(f[key])}</p>")
    return "".join(parts)
cards="".join(
    f"<details class='card sev-{sevof(f.get('severity'))}'><summary><span class='badge'>{esc(f.get('severity',''))}</span>"
    f" <b>{esc(f.get('id',''))}</b> {esc(f.get('title',''))}"
    f"<span class='meta'>{esc(f.get('confirmed',''))}{' · '+esc(f.get('files',f.get('file',''))) if f.get('files') or f.get('file') else ''}</span></summary>"
    f"<div class='body'>{finding_body(f)}</div></details>" for f in flist)
def gallery():
    md_=os.path.join(dest,"media"); out=[]
    if os.path.isfile(os.path.join(md_,"session.mp4")):
        out.append("<video controls preload=metadata src='media/session.mp4'></video>")
    shots=sorted(x for x in os.listdir(md_) if x.endswith(".png")) if os.path.isdir(md_) else []
    if shots:
        out.append("<div class='shots'>"+"".join(
            f"<a href='media/{esc(b)}'><figure><img loading=lazy src='media/{esc(b)}' alt=''><figcaption>{esc(b[3:-4].replace('-',' ') if b[:2].isdigit() else b[:-4])}</figcaption></figure></a>"
            for b in shots)+"</div>")
    note=os.path.join(md_,"GUI-did-not-run.txt")
    if os.path.isfile(note): out.append("<pre>"+esc(open(note,errors="replace").read()[:4000])+"</pre>")
    return "".join(out)
notes=[]
for f_,cls in (("timed-out.txt","warn"),("written-after.txt","warn")):
    if exists_beneath(os.path.join("logs",f_)): notes.append(f"<div class='note {cls}'>{esc(readf(os.path.join('logs',f_)).strip())}</div>")
if rep and rep.get("repo_tried_to_instruct_reviewer"): notes.append("<div class='note bad'>The repository contained text addressed to the reviewer.</div>")
lgxsum=readf(os.path.join("logs","lgx.sha256")).strip()
# Every package evaluated (a module may ship as several); the one a person
# opens, a view, leads.
PKGS=[p for p in (readjson(f) for f in files_beneath("logs") if re.fullmatch(r"logs/package(-.+)?\.json",f)) if isinstance(p,dict)]
PKGS.sort(key=lambda p:(not str(p.get("type","")).startswith("ui"),str(p.get("name"))))
PKG=PKGS[0] if PKGS else None
REBUILT=readjson(os.path.join("rebuild","rebuild.json"))
ORC=readf(os.path.join("logs","pipeline-commit")).strip()
ORC=ORC if re.fullmatch(r"[0-9a-f]{40}",ORC or "") else ""
def evaluated():
    """What exactly was evaluated (the Freeze rule wants one rootHash per
    review), and what checked it: the open-review commit."""
    if not PKGS:
        return "<div class=evaluated>Evaluated: the source at this commit (no published package given).</div>"
    return "".join(one(p) for p in PKGS)
def one(PKG):
    o=PKG.get("official") or {}
    sg=PKG.get("signature") or {}
    rb=(REBUILT.get(PKG.get("name")) or {}) if isinstance(REBUILT,dict) else {}
    v=rb.get("verdict")
    reb={"identical":"<b class=ok>rebuilt from this source: identical</b> ("+esc(", ".join(l.split()[1] for l in rb.get("compare",[]) if l.startswith("SAME     variants/")))+")",
         "differs":"<b class=red>rebuilt from this source: DIFFERS</b>",
         "not built":"not rebuilt (the build failed or found no flake; see rebuild/)",
         "nothing to compare":"rebuilt, but no platform in common to compare"}.get(v,"")
    if sg.get("valid"):
        sig=(f"<b class=ok>signed</b> (key <code>{esc(sg.get('key','')[:20])}…</code>"
             + (f", the repository's <code>{esc(sg['key_in_repository'])}</code>)" if sg.get("key_in_repository") else ", <b class=red>not a key in the repository</b>)"))
    elif sg: sig="<b class=red>signature does not verify</b>"
    else: sig="not signed"
    if o.get("error"): cat="the official catalogue couldn't be read"
    elif not o.get("listed"): cat="not in the official Logos catalogue"
    elif not o.get("version_listed"): cat="in the official catalogue, but not this version"
    elif o.get("rootHash_matches"): cat="in the official Logos catalogue, same rootHash"
    else: cat="<b class=red>the official catalogue lists this version with a different rootHash</b>"
    return (f"<div class=evaluated>Evaluated <b>{esc(PKG.get('name'))} {esc(PKG.get('version'))}</b> "
            f"({esc(PKG.get('type',''))}, {esc(', '.join(PKG.get('variants') or []))}) · rootHash <code>{esc(str(PKG.get('rootHash'))[:16])}…</code>"
            f" · sha256 <code>{esc(PKG.get('sha256','')[:16])}…</code> · {sig} · {cat}{(' · '+reb) if reb else ''}</div>")
imgid=readf(os.path.join("logs","image")).strip()[:19]
# When the review ran (the clock it was given), not when this page was made.
try: when=time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(int(readf(os.path.join("logs","clock")).split()[0])))
except Exception: when=time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime())
cost=(f"{U['est_cost_usd']:.2f} DIEM" if U.get("recorded") else "—")
chips="".join(f"<span class='chip sev-{v}'>{counts[v]} {v}</span>" for v in SEV if counts[v])
def block(title,body,cls=""):
    return f"<section class='{cls}'><h2>{title}</h2>{body}</section>" if body.strip() else ""
behaviour=(f"<ul class='beh'>{behrow}</ul>" if behrow else
           ("<p>Nothing recorded before it stopped.</p>" if FAILED else "<p class='ok'>Nothing flagged: no bait read or sent, no unexpected traffic.</p>"))
def storage_section():
    """The Logos Storage copy, once storage.py has made it; until then a
    placeholder it fills in (the page isn't rendered twice for it)."""
    try:
        import storage
        return storage.storage_html(json.load(open(os.path.join(dest,"storage.json"))))
    except Exception:
        return "<!--storage-->"
PAGE_CSS="""
:root{--bg:#0b0d10;--panel:#14181d;--line:#232a32;--fg:#d9dee4;--dim:#8b95a1;--acc:#6cc8ff;
--critical:#ff4d5e;--high:#ff8a3d;--medium:#f5c542;--low:#7bc8a4;--info:#8b95a1;--none:#5fd38d;--failed:#ff4d5e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:66em;margin:0 auto;padding:1.5em 1.2em 4em}a{color:var(--acc)}code,pre{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:.88em}
pre{background:#0f1317;border:1px solid var(--line);border-radius:8px;padding:.8em;overflow:auto;white-space:pre-wrap;word-break:break-word}
header.hero{background:linear-gradient(135deg,#141a21,#0f1216);border:1px solid var(--line);border-radius:14px;padding:1.4em 1.6em;margin-bottom:1.2em}
.hero h1{margin:.1em 0 .2em;font-size:1.9em;letter-spacing:-.01em}.hero .sub{color:var(--dim)}.hero .sub code{color:var(--fg)}
.verdict{display:inline-block;padding:.25em .8em;border-radius:999px;font-weight:700;font-size:.9em;color:#0b0d10}
.v-critical{background:var(--critical)}.v-high{background:var(--high)}.v-medium{background:var(--medium)}.v-low{background:var(--low)}.v-none{background:var(--none)}.v-failed{background:var(--failed)}
.chips{margin-top:.7em}.chip{display:inline-block;margin:.15em .3em .15em 0;padding:.1em .6em;border-radius:6px;border:1px solid var(--line);font-size:.85em}
.chip.sev-critical{color:var(--critical)}.chip.sev-high{color:var(--high)}.chip.sev-medium{color:var(--medium)}.chip.sev-low{color:var(--low)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(10em,1fr));gap:.6em;margin-top:1em}
.fact{background:#0f1317;border:1px solid var(--line);border-radius:8px;padding:.5em .8em}.fact b{display:block;color:var(--dim);font-weight:500;font-size:.8em;text-transform:uppercase;letter-spacing:.05em}
.evaluated{margin-top:.7em;padding:.45em .8em;border-radius:8px;background:#0f1317;border:1px solid var(--line);font-size:.9em;overflow-wrap:anywhere}
.note{border-radius:8px;padding:.6em 1em;margin:.6em 0;border:1px solid}.note.warn{border-color:#6b5520;background:#1d1a10;color:#f5c542}.note.bad{border-color:#6b2027;background:#1d1013;color:#ff8a8a}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1em 1.4em;margin:1em 0}
section h2{margin:.2em 0 .6em;font-size:1.15em}section h3,section h4,section h5{margin:.9em 0 .3em}
details.card{border:1px solid var(--line);border-left:4px solid var(--info);border-radius:8px;margin:.5em 0;background:#0f1317}
details.card summary{cursor:pointer;padding:.6em .9em;list-style:none}details.card summary::-webkit-details-marker{display:none}
details.card[open] summary{border-bottom:1px solid var(--line)}details.card .body{padding:.2em 1.1em .8em}
.card .meta{display:block;color:var(--dim);font-size:.82em;margin-top:.15em}
.badge{display:inline-block;min-width:5.2em;text-align:center;padding:.05em .5em;border-radius:5px;font-size:.78em;font-weight:700;color:#0b0d10;background:var(--info)}
.sev-critical{border-left-color:var(--critical)}.sev-critical .badge{background:var(--critical)}
.sev-high{border-left-color:var(--high)}.sev-high .badge{background:var(--high)}
.sev-medium{border-left-color:var(--medium)}.sev-medium .badge{background:var(--medium)}
.sev-low{border-left-color:var(--low)}.sev-low .badge{background:var(--low)}
ul.beh{padding-left:1.1em}ul.beh li{margin:.25em 0;overflow-wrap:anywhere}ul.beh details summary{cursor:pointer}.red{color:#ff8a8a}.ok{color:var(--none)}
video{width:100%;border-radius:8px;border:1px solid var(--line);background:#000}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(14em,1fr));gap:.7em;margin-top:.8em}
.shots figure{margin:0;background:#0f1317;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.shots img{width:100%;display:block;aspect-ratio:16/10;object-fit:cover;object-position:top}.shots figcaption{padding:.3em .6em;color:var(--dim);font-size:.82em}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:.35em .5em;text-align:left;vertical-align:top}th{color:var(--dim);font-weight:500;width:12em}
footer{color:var(--dim);font-size:.85em;margin-top:2em;border-top:1px solid var(--line);padding-top:1em}
"""
write("live.html", f"""<!doctype html><meta charset=utf-8><title>{esc(slug)} — done</title><style>{CSS}</style>
<h1>{esc(slug)}</h1><p>Review finished. <a href="index.html">Read the report →</a></p>""")
# What the review covered of what it had to (inventory.py, coverage.py).
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import coverage as _cov
FOCUS=readf(os.path.join("logs","focus")).strip() or "security"
INV=readjson("inventory.json"); COVJ=readjson("coverage.json")
COV=_cov.summary(INV,COVJ if isinstance(COVJ,dict) else {}) if isinstance(INV,dict) and INV.get("items") else None
def coverage_html():
    if not COV: return "<p>No inventory was made for this review: it predates them (2026-10-30), or the inventory failed.</p>"
    cj=COVJ if isinstance(COVJ,dict) else {}
    rows="".join(
        f"<tr><td><code>{esc(i['id'].split(':',1)[1])}</code></td><td>{esc(i.get('lines',''))}</td>"
        f"<td>{esc((cj.get(i['id']) or {}).get('status','not marked') if isinstance(cj.get(i['id']),dict) else 'not marked')}</td>"
        f"<td>{esc(str((cj.get(i['id']) or {}).get('note','') if isinstance(cj.get(i['id']),dict) else '')[:400])}"
        f"{'' if not why else ' <span class=red>('+esc(why)+')</span>'}</td></tr>"
        for i,why in ((i,_cov.judge(i,cj.get(i['id']))) for i in INV["items"]))
    scr="".join(f"<li>{esc(k[7:])}: {esc(str(v.get('note',''))[:300])}</li>" for k,v in cj.items()
                if k.startswith("screen:") and isinstance(v,dict))
    return (f"<p><b>Focus: {esc(FOCUS)}</b>: {esc(INV.get('scope',''))}. Listed from the source before the review "
            f"began: {INV.get('files',0)} files and {INV.get('methods',0)} exposed methods, {INV.get('lines',0):,} lines "
            f"in {', '.join(esc(r or '.') for r in INV.get('module_roots',[])) or 'the repository'}. "
            f"<b>Covered: {COV['covered']} of {COV['items']} items ({COV['pct']}%), {COV['lines_pct']}% of the lines.</b> "
            "An item counts only with a note on what was checked, and a file over 300 lines only when what was read "
            "spans 90% of it.</p>"
            + (f"<p>Screens: </p><ul>{scr}</ul>" if scr else "")
            + f"<details><summary>Every item</summary><table><tr><th>Item</th><th>Lines</th><th>Status</th><th>What was checked</th></tr>{rows}</table></details>"
            + (f"<p>Outside the module, not in scope: {len(INV.get('outside_module',[]))} files (a phone app, tools, a site…).</p>" if INV.get('outside_module') else ""))
modname=(readjson(os.path.join("src","metadata.json")) or {}).get("name") if isinstance(readjson(os.path.join("src","metadata.json")),dict) else None
title=modname or re.sub(r"-(security|p2p|ui|full)$","",slug).rsplit("-",1)[0]
write("index.html", f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>{esc(title)} — open review</title><style>{PAGE_CSS}</style><main>
<p><a href="/">← all reviews</a></p>
<header class=hero><span class='verdict v-{worst}'>{pill}</span>
<h1>{esc(title)}</h1>
<div class=sub><code>{esc(repo)}</code> @ <code>{esc(commit[:12])}</code></div>
<div class=chips>{chips}</div>
{evaluated()}
<div class=facts>
<div class=fact><b>Focus</b>{esc(FOCUS)}</div>
<div class=fact><b>Coverage</b>{f"{COV['pct']}% of {COV['items']} items" if COV else "not measured"}</div>
<div class=fact><b>Reviewed</b>{esc(when)}</div>
<div class=fact><b>Model</b>{esc(MODEL.split('/')[-1])}</div>
<div class=fact><b>Cost</b>{esc(cost)}</div>
<div class=fact><b>open-review</b>{f'<a href="https://github.com/vpavlin/open-review/tree/{ORC}"><code>{ORC[:12]}</code></a>' if ORC else 'not recorded'}</div>
</div></header>
{''.join(notes)}
{failed_html() if FAILED else ''}
{block('Bottom line', mdsafe.render(section('Bottom line'),shift=1) or (esc(rep.get('verdict_summary','')) if rep else ''))}
{block('What the module did', behaviour)}
{block(f'Findings ({len(flist)})', cards or "<p>See <a href='report.md'>report.md</a>.</p>") if not FAILED else ''}
{block('Screens and recording', gallery())}
{block('Coverage', coverage_html())}
{block('What is solid', mdsafe.render(section('What is solid'),shift=1))}
{block('What was not tested', mdsafe.render(section('Coverage and what I did not test','What I did not test','What was not tested'),shift=1) or ('<ul>'+nottested+'</ul>' if nottested else ''))}
{block('Suggested order', mdsafe.render(section('Suggested order'),shift=1))}
{block('What the reviewer ran', mdsafe.render(section('What I ran'),shift=1) or ('<ul>'+ran+'</ul>' if ran else ''))}
{block('Usage and cost', usage)}
{storage_section()}
<section><h2>Evidence</h2><ul>
<li><a href="report.md">report.md</a>: the reviewer's full writeup · <a href="report.json">report.json</a></li>
<li><a href="session.log">session.log</a>: the reviewer's session · <a href="gateway.jsonl">gateway.jsonl</a>: every model request and reply</li>
<li><a href="behaviour/">behaviour/</a>: strace, DNS, the proxies' request logs, bait, the sandbox's self-check · <a href="checks/">checks/</a>: gitleaks, osv-scanner, semgrep · <a href="media/">media/</a></li>
<li><a href="chain.txt">chain.txt</a>: the hash-chain root over every file of the run · <a href="live.txt">live.txt</a>: the running transcript</li></ul></section>
<footer>Triage, not approval: automated and imperfect. The module ran in a sandbox dressed as a laptop and instrumented; the host kernel is not hidden.
Reviewed by open-review {f'<a href="https://github.com/vpavlin/open-review/tree/{ORC}"><code>{ORC[:12]}</code></a>' if ORC else '(commit not recorded)'}; sandbox image <code>{esc(imgid or 'not recorded')}</code>{' · package sha256 <code>'+esc(lgxsum.split()[0])+'</code>' if lgxsum else ''}.</footer>
</main>""")
# For the list of reviews.
json.dump({"slug":slug,"title":title,"repo":repo,"commit":commit,"when":when,"verdict":worst,"pill":pill,
           "counts":counts,"cost":cost,"summary":(rep or {}).get("verdict_summary","") if isinstance((rep or {}).get("verdict_summary",""),str) else "",
           "failed":bool(FAILED),"lgx":lgxsum.split()[0] if lgxsum else "","package":PKG,"open_review_commit":ORC,"focus":FOCUS,
           "coverage":({k:COV[k] for k in ("items","covered","pct","lines_pct")} if COV else None),
           # A re-render keeps the Logos Storage copy storage.py made.
           "storage":(json.load(open(os.path.join(dest,"storage.json"))) if os.path.isfile(os.path.join(dest,"storage.json")) else None)},
          open(os.path.join(dest,"review.json"),"w"))
print("published:",dest)
