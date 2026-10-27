#!/usr/bin/env bash
# The review host joins the "review" mesh: a mesh of its own, with Václav's
# phone and the laptop, and none of his other machines. This host runs code we
# expect to be hostile; on the office mesh it would sit beside every machine
# whose agent lets a mesh member read its conversations.
#
# Needs podman (apt) and scripts/install.sh from the shrooms repo. The invite
# is minted on the laptop with the review mesh's admin key (Václav's
# passphrase): `sudo shrooms invite --mesh review --name openreview`.
set -euo pipefail
apt-get -qq -y install podman
bash install.sh prepare --name openreview
echo "now: shrooms join <TOKEN> --name openreview"
