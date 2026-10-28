#!/usr/bin/env bash
# Prove the review host can be rebuilt from this repository: a fresh Ubuntu
# 24.04 VM on this machine, set up only by host/00..40 from a clone of the
# repository, then one review of the leaky control with a stand-in for the
# model (fake-pi.sh), so no key and no budget are needed.
#
#   host/test/vm.sh up        make and boot the VM (plain qemu + KVM, as the
#                             audit lab does; ssh on 127.0.0.1:2290, http 8090)
#   host/test/vm.sh setup     run the host scripts in it, as an operator would
#   host/test/vm.sh verify    the stand-in review, and what it must show
#   host/test/vm.sh down|destroy
set -euo pipefail
D=${OR_VM_DIR:-$HOME/or-vm}; mkdir -p "$D"
IMG_URL=https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img
REF=${OR_REF:-main}
KEY=$D/id_ed25519
SSH=(ssh -i "$KEY" -p 2290 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR op@127.0.0.1)

up() {
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -f "$KEY"
  if [ ! -f "$D/base.img" ]; then
    curl -fsSL -o "$D/base.img.part" "$IMG_URL"
    want=$(curl -fsSL "${IMG_URL%/*}/SHA256SUMS" | awk '/ubuntu-24.04-server-cloudimg-amd64.img$/{print $1}')
    echo "$want  $D/base.img.part" | sha256sum -c --quiet && mv "$D/base.img.part" "$D/base.img"
  fi
  [ -f "$D/disk.qcow2" ] || qemu-img create -q -f qcow2 -F qcow2 -b "$D/base.img" "$D/disk.qcow2" 40G
  cat > "$D/user-data" <<EOF
#cloud-config
hostname: openreview
users:
  - name: op
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    shell: /bin/bash
    ssh_authorized_keys: ["$(cat "$KEY.pub")"]
EOF
  printf 'instance-id: or-vm\nlocal-hostname: openreview\n' > "$D/meta-data"
  cloud-localds "$D/seed.img" "$D/user-data" "$D/meta-data" 2>/dev/null \
    || genisoimage -quiet -output "$D/seed.img" -volid cidata -joliet -rock "$D/user-data" "$D/meta-data"
  # Not qemu's default 10.0.2.0/24: rootless podman's user-mode network uses
  # it too, inside its namespace, and there the VM's own address was a
  # neighbour, not the host: the sandbox couldn't reach the gateway, and its
  # self-check refused the review (2026-10-28). A real host on 10.0.2.x would
  # see the same.
  qemu-system-x86_64 -enable-kvm -cpu host -smp 6 -m 8192 \
    -drive file="$D/disk.qcow2",if=virtio -drive file="$D/seed.img",if=virtio,format=raw \
    -netdev user,id=n0,net=10.0.9.0/24,hostfwd=tcp:127.0.0.1:2290-:22,hostfwd=tcp:127.0.0.1:8090-:80 -device virtio-net,netdev=n0 \
    -daemonize -pidfile "$D/qemu.pid" -serial file:"$D/console.log" -display none
  for _ in $(seq 1 90); do "${SSH[@]}" true 2>/dev/null && { echo "up: ssh -i $KEY -p 2290 op@127.0.0.1"; return; }; sleep 5; done
  echo "the VM didn't come up; see $D/console.log"; exit 1
}

setup() {
  "${SSH[@]}" "set -e; sudo apt-get -qq update; sudo apt-get -qq -y install git >/dev/null
    rm -rf open-review && git clone -q https://github.com/vpavlin/open-review && cd open-review && git checkout -q $REF
    cd host && for s in 00-base.sh 10-shrooms.sh 20-web.sh 30-agent.sh 40-pipeline.sh 50-storage.sh; do
      echo \"=== \$s\"; sudo bash \$s 2>&1 | tail -25; done"
}

verify() {
  "${SSH[@]}" 'set -e; cd ~/open-review
    sudo install -d -o reviewer -g reviewer /home/reviewer/test-modules
    sudo cp -r test-modules/leaky-build /home/reviewer/test-modules/ && sudo chown -R reviewer: /home/reviewer/test-modules
    sudo install -o reviewer -m 755 host/test/fake-pi.sh /home/reviewer/fake-pi.sh
    # No model here: a dummy key gets the gateway started; nothing calls it.
    sudo -u reviewer bash -c "umask 077; [ -s ~/.pi/agent/.env ] || echo VENICE_INFERENCE_KEY=test-no-model > ~/.pi/agent/.env"
    sudo -iu reviewer bash -lc "REVIEW_TEST_PI=/home/reviewer/fake-pi.sh REVIEW_MAX_MIN=15 bash ~/pipeline/review.sh localdir:/home/reviewer/test-modules/leaky-build" | tail -4
    R=/home/reviewer/runs/leaky-build-HEAD
    echo "--- the sandbox checked itself: $(sudo grep -c "^ok" $R/behaviour/sandbox-check.txt) ok, $(sudo grep -c FAIL $R/behaviour/sandbox-check.txt) failed"
    sudo grep FAIL $R/behaviour/sandbox-check.txt || true
    echo "--- what the stand-in saw"; sudo cat $R/probes/fake-pi.out
    echo "--- what the record shows"; sudo jq -c "{bait_sent_out,http_requests,reviewer_requests}" $R/behaviour/summary.json
    echo "--- published: $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/leaky-build-HEAD/) report, $(ls /srv/reviews/leaky-build-HEAD/media/ 2>/dev/null | tr "\n" " ")"
    echo "--- the pipeline commit recorded: $(sudo cat $R/logs/pipeline-commit)"
    echo "--- on Logos Storage: $(sudo jq -r ".cid // \"no\"" /srv/reviews/leaky-build-HEAD/storage.json 2>/dev/null)"
    echo "--- services: queue $(sudo -iu reviewer env XDG_RUNTIME_DIR=/run/user/$(id -u reviewer) systemctl --user is-active open-review-queue), agent $(sudo -iu reviewer env XDG_RUNTIME_DIR=/run/user/$(id -u reviewer) systemctl --user is-active shrooms-agent)"'
}

case "${1:-}" in
  up) up ;;
  setup) setup ;;
  verify) verify ;;
  ssh) shift; "${SSH[@]}" "$@" ;;
  down) [ -f "$D/qemu.pid" ] && kill "$(cat "$D/qemu.pid")" 2>/dev/null; rm -f "$D/qemu.pid"; echo down ;;
  destroy) "$0" down; rm -f "$D/disk.qcow2" "$D/seed.img"; echo "destroyed (the base image stays)" ;;
  *) sed -n '2,15p' "$0" ;;
esac
