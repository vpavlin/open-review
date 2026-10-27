#!/usr/bin/env bash
# The review host's base: updated, named, SSH by key only, a deny-by-default
# firewall. Run as root on a fresh Ubuntu 24.04 (Contabo Cloud VPS 6).
#
# Ubuntu 24.04 because the sandbox shares the host's kernel and cannot hide its
# version: a stock Ubuntu kernel (6.8.0-*-generic) is what most Linux laptops show.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update
apt-get -qq -y upgrade
hostnamectl set-hostname openreview

# Key-only SSH. Contabo sets a root password at order time; it is no longer
# accepted once this is in.
cat > /etc/ssh/sshd_config.d/10-keys-only.conf <<CONF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
sshd -t
systemctl reload ssh

apt-get -qq -y install ufw unattended-upgrades
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

# The shrooms daemon (installed by host/10-shrooms.sh) needs WireGuard,
# its delivery node's TCP port and discovery, and traffic arriving over the
# mesh interface itself: a deny-by-default firewall hid the Duet's agent from
# the whole mesh until its interface was trusted (2026-10-25).
ufw allow 51820/udp comment "shrooms wireguard"
ufw allow 60000/tcp comment "shrooms delivery"
ufw allow 9000/udp comment "shrooms discovery"
