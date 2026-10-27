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
