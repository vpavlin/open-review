#!/usr/bin/env bash
# Finished reviews, served read-only from this host (PoC decision, 2026-10-27).
# Václav did not want the review host pushing to data.vpavlin.xyz, and a pull
# from there was more than a PoC needs. The cost, written down: an escape from
# the sandbox lands on the host that serves the published reviews, and could
# rewrite them; the hash chain and the Logos Storage copy (by CID) are what
# would show it.
#
# Every review carries text from a module we treat as hostile, so pages are
# rendered here with everything escaped, and served with a CSP that allows no
# scripts, frames, forms or outside resources (host/Caddyfile).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get -qq -y install caddy
mkdir -p /srv/reviews
# A domain (bash 20-web.sh or.vpavlin.xyz) is served over HTTPS too: Caddy
# gets its certificate from Let's Encrypt once the name points here (FR-15).
DOMAIN=${1:-}
cp Caddyfile /tmp/Caddyfile.or
if [ -n "$DOMAIN" ]; then
  printf '\n# By name, over HTTPS (a certificate from Let'"'"'s Encrypt).\n%s {\n\timport reviews\n}\n' "$DOMAIN" >> /tmp/Caddyfile.or
  ufw allow 443/tcp comment "reviews, read-only, https"
fi
install -m 0644 /tmp/Caddyfile.or /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy
ufw allow 80/tcp comment "reviews, read-only"
