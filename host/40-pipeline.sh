#!/usr/bin/env bash
# The review pipeline itself, from this checkout: run as root from the
# repository, after 00-base, 10-shrooms (or without a mesh), 20-web and
# 30-agent. Deploying a change is "git pull" here and running this again.
#
# It installs the pipeline and the sandbox for the reviewer user, fetches the
# pinned Basecamp AppImage and checks it, builds the pinned sandbox image,
# installs the user services (the queue, the agent's environment) and creates
# the intake session. What it can't do is say so at the end: the model key is
# typed by a person, never put in a file in this repository.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
U=reviewer; UH=/home/$U
BASECAMP_URL=https://github.com/logos-co/logos-basecamp/releases/download/0.3.2/LogosBasecamp-Desktop-v0.3.2-f2fae6-x86_64.AppImage
BASECAMP_SHA=983de0c7e282155d93c7e338da78e5b1a7a32112390a89be48d44700c3ade012
# As the reviewer user, with its systemd and pipefail: sudo -i re-parses the
# line in a login shell, so what needs its environment goes in a script.
as_u() { sudo -iu "$U" env XDG_RUNTIME_DIR=/run/user/$(id -u "$U") bash -lc "set -o pipefail; $1"; }
apt-get -qq -y install rsync >/dev/null

echo "== the pipeline and the sandbox, from $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo 'this copy')"
install -d -o $U -g $U "$UH/pipeline" "$UH/sandbox" "$UH/intake" "$UH/queue" "$UH/.config/systemd/user"
rsync -a --delete --exclude __pycache__ "$REPO/pipeline/" "$UH/pipeline/"
rsync -a "$REPO/sandbox/" "$UH/sandbox/"
git -C "$REPO" rev-parse HEAD > "$UH/pipeline/.commit" 2>/dev/null || echo unknown > "$UH/pipeline/.commit"
install -m 644 "$REPO/host/intake/AGENTS.md" "$UH/intake/AGENTS.md"
chown -R $U:$U "$UH/pipeline" "$UH/sandbox" "$UH/intake"

echo "== Basecamp 0.3.2, checked against its hash"
if ! echo "$BASECAMP_SHA  $UH/sandbox/Basecamp.AppImage" | sha256sum -c --status 2>/dev/null; then
  curl -fsSL -o "$UH/sandbox/Basecamp.AppImage.part" "$BASECAMP_URL"
  echo "$BASECAMP_SHA  $UH/sandbox/Basecamp.AppImage.part" | sha256sum -c --status
  mv "$UH/sandbox/Basecamp.AppImage.part" "$UH/sandbox/Basecamp.AppImage"
fi
chmod 755 "$UH/sandbox/Basecamp.AppImage"; chown $U:$U "$UH/sandbox/Basecamp.AppImage"

echo "== the sandbox image (pinned; several minutes the first time)"
as_u "cd ~/sandbox && podman build -q -f reviewer.Containerfile -t localhost/open-reviewer:latest . | tail -1"

echo "== where reviews are published"
install -d -o $U -g $U /srv/reviews
as_u "python3 ~/pipeline/index.py /srv/reviews"

echo "== the user services"
cp -r "$REPO/host/user-units/." "$UH/.config/systemd/user/"
chown -R $U:$U "$UH/.config"
as_u "systemctl --user daemon-reload && systemctl --user enable --now open-review-queue.service && systemctl --user restart shrooms-agent.service"

echo "== the intake session"
as_u "bash ~/pipeline/intake-session.sh"

echo "== left to do by hand"
if [ -s "$UH/.pi/agent/.env" ] && grep -q '^VENICE_INFERENCE_KEY=.' "$UH/.pi/agent/.env"; then
  echo "   (nothing: the model key is in place)"
else
  echo "   the model key, typed, never pasted into a chat or a file in git:"
  echo "     sudo -u $U bash -c 'read -rsp \"Venice key: \" k; echo; umask 077; printf \"VENICE_INFERENCE_KEY=%s\\n\" \"\$k\" > ~/.pi/agent/.env'"
  echo "   then: sudo -iu $U systemctl --user restart shrooms-agent"
fi
echo "   WhisperBox submissions (optional): host/45-whisperbox.sh <dir with the bot's build>"
