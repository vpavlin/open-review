#!/usr/bin/env python3
# A logging forwarder in front of Venice. pi points at it instead of the real
# API, so (1) the Venice key stays here and never enters a sandbox, and (2)
# every model request and reply is logged to a review's gateway.jsonl, with a
# redaction pass, and a running human-readable transcript is appended for the
# live view. OpenAI-compatible: forwards /chat/completions to Venice.
import os,sys,json,time,re,urllib.request,http.server,hashlib,threading
VENICE=os.environ.get("GATEWAY_UPSTREAM","https://api.venice.ai/api/v1/chat/completions")
# Seconds between retries of a provider error; overridable for tests.
WAITS=[int(x) for x in os.environ.get("GATEWAY_RETRY_WAITS","5,15,45,120,300,600").split(",") if x]
KEY=os.environ["VENICE_INFERENCE_KEY"]
TOKEN=os.environ.get("REVIEW_TOKEN","")
# The write-up gets its own token: testing stops at BUDGET*TEST_SHARE, and
# only the report may spend the rest. Nothing goes past BUDGET, whatever the
# repository talks the model into (a review is capped, Václav 2026-10-28).
REPORT_TOKEN=os.environ.get("REPORT_TOKEN","")
# Only the review's own model is forwarded: a request naming a dearer one
# was priced at the default and slipped under the cap (FR-5, 2026-10-28).
MODEL=os.environ.get("REVIEW_MODEL","deepseek-v4-1-flash-1017")
BUDGET=float(os.environ.get("REVIEW_BUDGET","1.0"))
TEST_SHARE=float(os.environ.get("REVIEW_TEST_SHARE","0.8"))
# Venice's price per million tokens (input, cached input, output), in DIEM,
# which is also its USD price. 2026-10-28.
PRICES={"deepseek-v4-1-flash-uncensored":(0.33,0.00825,1.32),
        "deepseek-v4-1-flash-1017":(0.30,0.0075,1.20),"deepseek-v4-1-flash":(0.30,0.0075,1.20)}
SPENT={"total":0.0,"last":0.0}; LOCK=threading.Lock()
def cost(model,u):
    pi,pc,po=PRICES.get((model or "").split("/")[-1],(0.33,0.00825,1.32))
    pin=u.get("prompt_tokens",0) or 0; cached=(u.get("prompt_tokens_details") or {}).get("cached_tokens",0) or 0
    return ((pin-cached)*pi+cached*pc+(u.get("completion_tokens",0) or 0)*po)/1e6
def save_spend():
    os.makedirs(os.path.join(RUN,"logs"),exist_ok=True)
    with open(os.path.join(RUN,"logs","spend.json"),"w") as f:
        json.dump({"spent":round(SPENT["total"],4),"budget":BUDGET,"testing":round(BUDGET*TEST_SHARE,4)},f)
BIND=os.environ.get("GATEWAY_BIND","127.0.0.1")
RUN=os.environ.get("REVIEW_RUN","/tmp")           # where to log this review
PORT=int(os.environ.get("GATEWAY_PORT","7399"))
SECRET=re.compile(r'(gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN[^-]+PRIVATE KEY-----|CANARY-[A-Za-z0-9]{12})')
def redact(s): return SECRET.sub('[redacted]', s) if isinstance(s,str) else s
def deep(o):
    if isinstance(o,dict): return {k:deep(v) for k,v in o.items()}
    if isinstance(o,list): return [deep(v) for v in o]
    return redact(o)
def unstream(raw):
    """A streamed (SSE) completion put back together as one response: the text,
    the reasoning, the tool calls and the usage. pi always streams; logging the
    raw body as JSON failed silently and every reply and token count was lost
    (2026-10-27)."""
    msg={"content":"","reasoning_content":""}; calls={}; usage=None; finish=None; model=None
    for line in raw.decode("utf-8","replace").splitlines():
        if not line.startswith("data:"): continue
        data=line[5:].strip()
        if not data or data=="[DONE]": continue
        try: c=json.loads(data)
        except Exception: continue
        model=c.get("model",model)
        if c.get("usage"): usage=c["usage"]
        for ch in c.get("choices") or []:
            d=ch.get("delta") or {}
            msg["content"]+=d.get("content") or ""
            msg["reasoning_content"]+=d.get("reasoning_content") or d.get("reasoning") or ""
            for tc in d.get("tool_calls") or []:
                t=calls.setdefault(tc.get("index",0),{"id":"","type":"function","function":{"name":"","arguments":""}})
                if tc.get("id"): t["id"]=tc["id"]
                f=tc.get("function") or {}
                t["function"]["name"]+=f.get("name") or ""
                t["function"]["arguments"]+=f.get("arguments") or ""
            finish=ch.get("finish_reason") or finish
    if calls: msg["tool_calls"]=[calls[i] for i in sorted(calls)]
    return {"streamed":True,"model":model,"choices":[{"message":msg,"finish_reason":finish}],"usage":usage or {}}

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        auth=self.headers.get('Authorization','')
        if REPORT_TOKEN and auth=='Bearer '+REPORT_TOKEN: phase="report"
        elif not TOKEN or auth=='Bearer '+TOKEN: phase="testing"
        else:
            self.send_response(403); self.end_headers(); self.wfile.write(b'{"error":"forbidden"}'); return
        body=self.rfile.read(int(self.headers.get('Content-Length',0)))
        try: req=json.loads(body)
        except Exception: req={}
        if (req.get("model") or "").split("/")[-1]!=MODEL or MODEL not in PRICES:
            self.send_response(400); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps({"error":{"message":f"only {MODEL} is served here"}}).encode()); return
        # Refused before it is sent if it would go over: the next call is
        # guessed to cost a little more than the last.
        limit=BUDGET if phase=="report" else BUDGET*TEST_SHARE
        with LOCK: spent,last=SPENT["total"],SPENT["last"]
        if spent+max(last,0.002)*1.2 > limit:
            msg=(f"Review budget spent: {spent:.3f} of {limit:.2f} DIEM for {phase}. "
                 + ("Stop testing; the report is written next." if phase=="testing" else "Nothing more can be spent."))
            with open(os.path.join(RUN,"logs",f"budget-spent-{phase}.txt"),"w") as f: f.write(msg+"\n")
            with open(os.path.join(RUN,"gateway.jsonl"),"a") as f:
                f.write(json.dumps({"t":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"status":402,"phase":phase,"budget_refused":msg})+"\n")
            with open(os.path.join(RUN,"live.txt"),"a") as f: f.write("\n("+msg+")\n")
            self.send_response(402); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps({"error":{"message":msg,"type":"budget_exhausted"}}).encode()); return
        r=urllib.request.Request(VENICE,data=body,method='POST',
            headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
        t0=time.time()
        # A provider error is retried, waiting longer each time (about 25
        # minutes in all), so an outage pauses a review rather than ending it:
        # forumer's second run lost two hours to three 500s from Venice
        # (2026-10-27). Each failed attempt is logged too.
        ctype='application/json'
        for wait in WAITS+[None]:
            try:
                resp=urllib.request.urlopen(r,timeout=300); out=resp.read(); code=resp.status
                ctype=resp.headers.get('Content-Type',ctype)
            except urllib.error.HTTPError as e:
                out=e.read(); code=e.code
            except (urllib.error.URLError,TimeoutError,ConnectionError) as e:
                out=json.dumps({"error":"gateway: "+str(e)}).encode(); code=502
            if code<500 and code!=429 or wait is None: break
            with open(os.path.join(RUN,"gateway.jsonl"),"a") as f:
                f.write(json.dumps({"t":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"status":code,
                    "retry_in_s":wait,"model":req.get("model"),"error":out[:300].decode("utf-8","replace")})+"\n")
            with open(os.path.join(RUN,"live.txt"),"a") as f:
                f.write(f"\n(model provider answered {code}; retrying in {wait}s)\n")
            time.sleep(wait)
        if code>=500 or code==429:
            # Out of retries: the review can't be trusted to have been done,
            # so the pipeline fails it rather than publishing a partial one.
            os.makedirs(os.path.join(RUN,"logs"),exist_ok=True)
            with open(os.path.join(RUN,"logs","inference-failed.txt"),"a") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())} {req.get('model')} answered {code} "
                        f"after every retry: {out[:300].decode('utf-8','replace')}\n")
        try: rj=json.loads(out)
        except Exception: rj=unstream(out) if req.get("stream") else {"unparsed":out[:2000].decode("utf-8","replace")}
        c=cost(req.get("model"),(rj.get("usage") if isinstance(rj,dict) else None) or {})
        with LOCK:
            SPENT["total"]+=c
            if c: SPENT["last"]=c
            save_spend()
        rec={"t":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"ms":int((time.time()-t0)*1000),
             "status":code,"model":req.get("model"),"phase":phase,"cost":round(c,6),"request":deep(req),"response":deep(rj)}
        with open(os.path.join(RUN,"gateway.jsonl"),"a") as f: f.write(json.dumps(rec)+"\n")
        # running transcript for the live view: the user turn and the model's reply, redacted
        try:
            msgs=req.get("messages",[]); last=msgs[-1]["content"] if msgs else ""
            m=rj.get("choices",[{}])[0].get("message",{})
            ans=m.get("content","") or ""
            for tc in m.get("tool_calls") or []:
                ans+="\n→ "+tc["function"]["name"]+" "+tc["function"]["arguments"][:1500]
            live=os.path.join(RUN,"live.txt")
            with open(live,"a") as f:
                f.write("\n▶ "+redact(str(last))[:4000]+"\n\n"+redact(str(ans))+"\n")
        except Exception: pass
        self.send_response(code); self.send_header('Content-Type',ctype); self.end_headers()
        self.wfile.write(out)
if __name__=="__main__":
    save_spend()
    http.server.ThreadingHTTPServer((BIND,PORT),H).serve_forever()
