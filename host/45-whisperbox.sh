#!/usr/bin/env bash
# Optional: community submissions through WhisperBox (whisperbox-bot.md).
# Needs the bot's build, which isn't public yet: a directory with
# whisperbox_core 0.5.0 and its dependencies as .lgx, logosctl's AppImage and
# SHA256SUMS (atlas/whisperbox's drop, 2026-10-28). Run as root, after 40.
set -euo pipefail
DIST=${1:?usage: 45-whisperbox.sh <dir with the bot build and SHA256SUMS>}
(cd "$DIST" && sha256sum -c --quiet SHA256SUMS)
U=reviewer; UH=/home/$U
install -d -o $U -g $U "$UH/wb-bot" "$UH/wb-bot/dist"
cp "$DIST"/* "$UH/wb-bot/dist/"; chown -R $U:$U "$UH/wb-bot"
apt-get -qq -y install libgl1 libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3 >/dev/null
mkdir -p /opt/logosctl && cd /opt/logosctl
cp "$UH/wb-bot/dist/logosctl-x86_64.AppImage" . && chmod +x logosctl-x86_64.AppImage
rm -rf squashfs-root && ./logosctl-x86_64.AppImage --appimage-extract >/dev/null
ln -sf /opt/logosctl/squashfs-root/usr/bin/logosctl /usr/local/bin/logosctl
sudo -iu $U env XDG_RUNTIME_DIR=/run/user/$(id -u $U) bash -lc \
  "systemctl --user daemon-reload && systemctl --user enable --now wb-bot.service wb-bot-poll.service && sleep 60 && python3 ~/pipeline/whisperbox.py identity"
echo "now in WhisperBox: create the form, add the pubHex above as co-owner, then"
echo "  sudo -iu $U python3 ~/pipeline/whisperbox.py join 'whisperbox://form?id=…&by=0x…'"
