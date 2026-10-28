# The recording proxy's log (a mitmdump addon): one JSON line per request the
# sandbox's user made over HTTP or HTTPS, so a review states what was sent
# where instead of inferring it from DNS lookups and connect() calls. The
# proxy and this file are root's; the user under review can neither stop
# them nor write the log.
#
#   mitmdump --mode transparent -s proxy_log.py --set review_log=<file>
import json, time
from mitmproxy import ctx

BODY = 4096  # how much of each request body is kept; enough to see a canary


def text(b):
    if not b:
        return ""
    s = b[:BODY].decode("utf-8", "replace")
    return s + ("…" if len(b) > BODY else "")


class Log:
    def load(self, loader):
        loader.add_option("review_log", str, "/run/behaviour/proxy.jsonl", "where to log")

    def _write(self, rec):
        rec["t"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(ctx.options.review_log, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def response(self, flow):
        q, r = flow.request, flow.response
        self._write({"method": q.method, "url": q.pretty_url, "host": q.pretty_host,
                     "server": f"{flow.server_conn.address[0]}:{flow.server_conn.address[1]}" if flow.server_conn.address else "",
                     "sent_bytes": len(q.raw_content or b""), "sent": text(q.raw_content),
                     "status": r.status_code, "received_bytes": len(r.raw_content or b"")})

    def error(self, flow):
        q = flow.request
        self._write({"method": q.method, "url": q.pretty_url, "host": q.pretty_host,
                     "sent_bytes": len(q.raw_content or b""), "sent": text(q.raw_content),
                     "error": str(flow.error)})

    def tls_failed_client(self, data):
        # The client refused our certificate: it pins, or brings its own trust
        # store. What it then sends is not readable, but that it tried is.
        c = data.context
        self._write({"tls_refused_by_client": True, "sni": c.client.sni or "",
                     "server": f"{c.server.address[0]}:{c.server.address[1]}" if c.server.address else ""})


addons = [Log()]
