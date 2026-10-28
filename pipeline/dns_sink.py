#!/usr/bin/env python3
# A logging resolver + connection sink for the sandbox. It logs every hostname
# a module looks up. Hosts needed to build (npm, github, nodejs, debian) are
# forwarded to a real resolver so the build works; every other host is answered
# with 127.0.0.1 and its later connection is caught by a local sink that logs
# what was sent. So a module reaching for an unexpected host, and anything it
# tries to send there, is recorded.
import sys,socket,struct,time,threading
LOG=open(sys.argv[1],"a")
def log(tag,msg): LOG.write(f"{time.strftime('%H:%M:%S')} {tag} {msg}\n"); LOG.flush()
ALLOW=("registry.npmjs.org","npmjs.org","github.com","githubusercontent.com","nodejs.org",
       "debian.org","ubuntu.com","pypi.org","pythonhosted.org","deb.nodesource.com","cloudflare.com")
UP=("1.1.1.1",53)
# "forward" (default): every name is logged and resolved, so the module works
# as it would for a user (forumer's node needs logos.dev). "sinkhole": only
# the build hosts resolve and the rest land on the local sink, which logs
# what is sent; the module's own networking then fails.
MODE=(sys.argv[2] if len(sys.argv)>2 else "forward")
def qname(d,o):
    p=[]
    while d[o]: n=d[o]; p.append(d[o+1:o+1+n].decode('latin1')); o+=1+n
    return ".".join(p),o+1
def dns():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("127.0.0.1",53))
    while True:
        try:
            data,addr=s.recvfrom(512); qn,off=qname(data,12)
            allowed=MODE=="forward" or any(qn==a or qn.endswith("."+a) for a in ALLOW)
            log("dns", qn+("" if allowed else "  [sinkholed]"))
            if allowed:
                try:
                    u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); u.settimeout(4)
                    u.sendto(data,UP); r,_=u.recvfrom(1024); s.sendto(r,addr); continue
                except Exception: pass
            r=data[:2]+b'\x81\x80'+data[4:6]+data[4:6]+b'\x00\x00\x00\x00'+data[12:off+3]
            r+=b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'+socket.inet_aton("127.0.0.1")
            s.sendto(r,addr)
        except Exception: pass
def tcp(port):
    s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try: s.bind(("127.0.0.1",port)); s.listen(8)
    except Exception: return
    while True:
        try:
            c,_=s.accept(); c.settimeout(3)
            try: first=c.recv(1024)
            except Exception: first=b""
            host=""
            try:
                import re
                m=re.search(rb'[a-z0-9.-]+\.(net|com|org|io|xyz|cc|ru)\b',first)
                if m: host=m.group(0).decode()
            except Exception: pass
            log("conn", f"port {port} {host} bytes={len(first)}")
        except Exception: pass
threading.Thread(target=tcp,args=(443,),daemon=True).start()
threading.Thread(target=tcp,args=(80,),daemon=True).start()
dns()
