#!/usr/bin/env python3
# A logging forwarder in front of Venice. pi points at it instead of the real
# API, so (1) the Venice key stays here and never enters a sandbox, and (2)
# every model request and reply is logged to a review's gateway.jsonl, with a
# redaction pass, and a running human-readable transcript is appended for the
# live view. OpenAI-compatible: forwards /chat/completions to Venice.
import os,sys,json,time,re,urllib.request,http.server,hashlib
VENICE="https://api.venice.ai/api/v1/chat/completions"
KEY=os.environ["VENICE_INFERENCE_KEY"]
TOKEN=os.environ.get("REVIEW_TOKEN","")
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
        if TOKEN and self.headers.get('Authorization','') != 'Bearer '+TOKEN:
            self.send_response(403); self.end_headers(); self.wfile.write(b'{"error":"forbidden"}'); return
        body=self.rfile.read(int(self.headers.get('Content-Length',0)))
        try: req=json.loads(body)
        except Exception: req={}
        r=urllib.request.Request(VENICE,data=body,method='POST',
            headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
        t0=time.time()
        ctype='application/json'
        try:
            resp=urllib.request.urlopen(r,timeout=300); out=resp.read(); code=resp.status
            ctype=resp.headers.get('Content-Type',ctype)
        except urllib.error.HTTPError as e:
            out=e.read(); code=e.code
        try: rj=json.loads(out)
        except Exception: rj=unstream(out) if req.get("stream") else {"unparsed":out[:2000].decode("utf-8","replace")}
        rec={"t":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"ms":int((time.time()-t0)*1000),
             "status":code,"model":req.get("model"),"request":deep(req),"response":deep(rj)}
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
    http.server.ThreadingHTTPServer((BIND,PORT),H).serve_forever()
