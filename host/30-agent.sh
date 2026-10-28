#!/usr/bin/env bash
# The reviewer's agent: shrooms-agent as its own unprivileged user, pi as the
# harness of its intake session (host/intake), from a pinned commit and image.
#
# The Venice key is a key of its own for open review, with a spend limit.
# Václav typed it on this host (read -rs, never in a chat); it lives only in
# /home/reviewer/.pi/agent/.env, mode 600 (40-pipeline.sh says how). pi's
# models.json names it as $VENICE_INFERENCE_KEY.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SHROOMS_REF=8388f96a9cbabeacb6f3d84f095c6de51976530c
AGENT_IMAGE=ghcr.io/vpavlin/shrooms-agent@sha256:784ab13751f0a9c5bf3cb49cecfc13a2aea95e97a62b913c3243e0a69f9786b7
PI_VERSION=1.4.0
id reviewer >/dev/null 2>&1 || useradd -m -s /bin/bash reviewer
loginctl enable-linger reviewer
curl -fsSL -o /tmp/install-agent.sh "https://raw.githubusercontent.com/vpavlin/logos-vpn/$SHROOMS_REF/scripts/install-agent.sh"
bash /tmp/install-agent.sh --user reviewer --image "$AGENT_IMAGE"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get -qq -y install nodejs=22.23.4-1nodesource1
sudo -u reviewer -H bash -lc "npm config set prefix ~/.local && npm i -g @earendil-works/pi-coding-agent@$PI_VERSION"
install -d -o reviewer -g reviewer -m 700 /home/reviewer/.pi /home/reviewer/.pi/agent
install -o reviewer -g reviewer -m 600 "$HERE/models.json" /home/reviewer/.pi/agent/models.json
