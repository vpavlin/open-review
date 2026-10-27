#!/usr/bin/env python3
# Turn the raw capture into a behaviour summary and grade it against the bait:
# which bait files were read, which hosts were contacted, and whether any bait
# canary left the box.
import sys,os,json,re
B=sys.argv[1]
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
hosts=sorted({l.split(' ',1)[1].strip() for l in dns.splitlines() if ' ' in l})
local=('127.0.0.1','::1','localhost')
ext_hosts=[h for h in hosts if not any(h==x or h.endswith('.localhost') for x in local)]
connects=sorted(set(re.findall(r'connect\([^,]*,\s*\{sa_family=AF_INET6?,[^}]*?(?:inet6?_addr|sin6?_addr[^,]*|"[0-9a-f:.]+")[^}]*\}',strace)))
# did a canary leave? (the sink would have logged the body if TLS allowed; here
# we flag read-then-contact, the strongest we capture without TLS MITM)
exfil = bool(bait_read) and bool(ext_hosts)
summary={
 "bait_files_read": bait_read,
 "contacted_hosts": ext_hosts,
 "read_secret_then_contacted_external_host": exfil,
 "build_tail": build[-1500:],
 "opens_count": len(opens), "failed_opens_sample": sorted(fails)[:10],
}
print(json.dumps(summary,indent=1))
