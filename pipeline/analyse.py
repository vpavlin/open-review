#!/usr/bin/env python3
# Turn the raw capture into a behaviour summary and grade it against the bait:
# which bait files were read, which hosts were contacted, and whether any bait
# canary left the box.
import sys,os,json,re
B=sys.argv[1]
GW=sys.argv[2] if len(sys.argv)>2 else ""   # the review's own gateway, host:port
def readf(p):
    try: return open(os.path.join(B,p),encoding='latin1').read()
    except: return ""
strace=readf("strace.log"); dns=readf("dns.log"); build=readf("build.out")
bait=json.load(open(os.path.join(B,"bait.json"))) if os.path.exists(os.path.join(B,"bait.json")) else {}
# files opened (and failed) outside the module's own tree
opens=set(re.findall(r'openat?\([^,]*,\s*"([^"]+)"',strace))
fails=set(re.findall(r'openat?\([^)]*"([^"]+)"[^)]*=\s*-1',strace))
bait_read=[p for p in bait if p in opens]
# hosts contacted by name (dns sink) and raw IP connects
hosts=sorted({p[2] for p in (l.split() for l in dns.splitlines()) if len(p)>=3 and p[1]=="dns"})
local=('127.0.0.1','::1','localhost')
ext_hosts=[h for h in hosts if not any(h==x or h.endswith('.localhost') for x in local)]
# Every outbound address, by IP and port: a module that skips DNS and
# connects to an address directly was never reported (FR-3, 2026-10-28).
connects=set()
for m in re.finditer(r'connect\([^,]*,\s*\{sa_family=AF_INET6?,([^}]*)\}',strace):
    a=m.group(1); port=re.search(r'htons\((\d+)\)',a)
    ip=re.search(r'inet_addr\("([^"]+)"\)|inet_pton\(AF_INET6,\s*"([^"]+)"',a)
    if not (port and ip): continue
    ip=ip.group(1) or ip.group(2); hp=f"{ip}:{port.group(1)}"
    if ip.startswith("127.") or ip in ("::1","0.0.0.0","::") or port.group(1)=="0": continue
    if GW and hp.endswith(":"+GW.rsplit(":",1)[-1]): continue
    connects.add(hp)
connects=sorted(connects)
# did a canary leave? (the sink would have logged the body if TLS allowed; here
# we flag read-then-contact, the strongest we capture without TLS MITM)
exfil = bool(bait_read) and bool(ext_hosts or connects)
summary={
 "bait_files_read": bait_read,
 "contacted_hosts": ext_hosts,
 "connected_addresses": connects[:200],
 "read_secret_then_contacted_external_host": exfil,
 "build_tail": build[-1500:],
 "opens_count": len(opens), "failed_opens_sample": sorted(fails)[:10],
}
print(json.dumps(summary,indent=1))
