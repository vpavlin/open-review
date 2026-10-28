#!/usr/bin/env bash
# Optional: reviews mirrored to Logos Storage. A Logos Storage node (v0.5.3,
# pinned by hash) on the logos.test network runs as the reviewer user; each
# published review is uploaded as one archive and its CID shown on the page
# and the front page. The node is the archive's only holder unless someone
# else fetches it: this is content addressing, not paid durability.
#
#   bash 50-storage.sh [public IP]     as root, after 40
set -euo pipefail
U=reviewer; UH=/home/$U
URL=https://github.com/logos-storage/logos-storage-nim/releases/download/v0.5.3/logos-storage-linux-amd64-v0.5.3.zip
SHA=1086fae4f283cab882f133abe4d5a88cfae8d61edba9f0094c7f75b368ec9d56
IP=${1:-}
apt-get -qq -y install unzip >/dev/null
install -d -o $U -g $U "$UH/storage"
if [ ! -x /opt/logos-storage/logos-storage ]; then
  curl -fsSL -o /tmp/ls.zip "$URL"; echo "$SHA  /tmp/ls.zip" | sha256sum -c --quiet
  mkdir -p /opt/logos-storage && unzip -o -q /tmp/ls.zip -d /opt/logos-storage
  mv /opt/logos-storage/logos-storage-linux-amd64-v0.5.3 /opt/logos-storage/logos-storage
fi
# Peers reach the node on 8070; its REST API stays on localhost.
ufw allow 8070/tcp comment "logos storage" >/dev/null
nat=auto; [ -n "$IP" ] && nat="extip:$IP"
cat > "$UH/.config/systemd/user/logos-storage.service" <<UNIT
[Unit]
Description=open-review: a Logos Storage node holding the published reviews
After=network-online.target

[Service]
ExecStart=/opt/logos-storage/logos-storage --data-dir=%h/storage --network=logos.test --listen-port=8070 --api-port=8099 --nat=$nat
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
UNIT
chown $U:$U "$UH/.config/systemd/user/logos-storage.service"
sudo -iu $U env XDG_RUNTIME_DIR=/run/user/$(id -u $U) bash -lc "systemctl --user daemon-reload && systemctl --user enable --now logos-storage.service && sleep 20 && systemctl --user is-active logos-storage"
