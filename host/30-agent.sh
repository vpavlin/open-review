#!/usr/bin/env bash
# The reviewer's agent: shrooms-agent as its own unprivileged user, pi as the
# harness, Venice behind the agent's gateway.
#
# The Venice key is a key of its own for open review, with a spend limit.
# Václav typed it on this host (read -rs, never in a chat); it lives only in
# /home/reviewer/.pi/agent/.env, mode 600. pi's models.json names it as
# $VENICE_INFERENCE_KEY: a cage gets the gateway's dummy key, never this one
# (shrooms ADR-059).
set -euo pipefail
id reviewer >/dev/null 2>&1 || useradd -m -s /bin/bash reviewer
loginctl enable-linger reviewer
bash install-agent.sh --user reviewer          # from the shrooms repo
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get -qq -y install nodejs
sudo -u reviewer -H bash -lc 'npm config set prefix ~/.local && npm i -g @earendil-works/pi-coding-agent'
install -d -o reviewer -g reviewer -m 700 /home/reviewer/.pi /home/reviewer/.pi/agent
install -o reviewer -g reviewer -m 600 models.json /home/reviewer/.pi/agent/models.json
