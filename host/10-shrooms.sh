#!/usr/bin/env bash
# The review host joins the "review" mesh: a mesh of its own, with Václav's
# phone and the laptop, and none of his other machines. This host runs code we
# expect to be hostile; on the office mesh it would sit beside every machine
# whose agent lets a mesh member read its conversations.
#
# shrooms' installer comes from the shrooms repository at a pinned commit and
# installs a pinned daemon image. The invite is minted on the laptop with the
# review mesh's admin key (Václav's passphrase):
#   sudo shrooms invite --mesh review --name openreview
# Without a mesh the host still works: the agent serves this machine alone.
set -euo pipefail
SHROOMS_REF=8388f96a9cbabeacb6f3d84f095c6de51976530c
SHROOMS_IMAGE=ghcr.io/vpavlin/shrooms@sha256:a94b0957dfa9d267d76212e76de7dc19b25ae9deb9eaa039bc758079a3ae40fa
apt-get -qq -y install podman curl
curl -fsSL -o /tmp/shrooms-install.sh "https://raw.githubusercontent.com/vpavlin/logos-vpn/$SHROOMS_REF/scripts/install.sh"
bash /tmp/shrooms-install.sh --image "$SHROOMS_IMAGE" prepare --name openreview
echo "then, with an invite: shrooms join <TOKEN> --name openreview"
