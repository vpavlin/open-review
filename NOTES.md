# Notes

A running log: newest last. What was done, why, and what was found.

## 2026-10-27: the idea and the host

- Proposal written after a conversation with Václav (docs/proposal.md). Decided:
  - **Scope:** Basecamp modules first.
  - **Base tier:** proper testing for every submission: build, install, use every feature, attack, record.
  - **Recording:** reads (and refused reads), writes (an overlay diff), network, processes, resources.
  - **Bait:** fake secrets planted around the home directory.
  - **Disguise:** the sandbox dressed as one of three real laptops (XPS 13 9340, ThinkPad X1 Carbon Gen 12, Framework 13 AMD), picked at random per run.
  - **Publishing:** all of it public.
  - **Later, after the PoC:** TEE models, a confidential VM, chain timestamps, the live view.
- Venice TEE checked (samples in the laptop's ~/notes/venice-tee-signature-sample-20261027):
  - **Works:** the hardware attestation (NEAR AI, Intel TDX plus NVIDIA Hopper).
  - **Doesn't close yet:** the per-response signature is a gateway key that's not in the attestation, over hashes we can't recompute.
- **Host:** a Contabo Cloud VPS 6 (6 vCPU, 12 GB, 200 GB), Ubuntu 24.04, kernel 6.8.0-147-generic, KVM guest, 77.237.236.27.
  - **Why Contabo:** Hetzner was €36–70 a month for this size.
  - **Why no nested VM:** the rented VM is itself the isolation boundary; the disguised container runs inside it.
- `host/00-base.sh` applied:
  - updates;
  - hostname `openreview`;
  - SSH keys only;
  - ufw deny-in with only 22 open.
  - Login: `ssh openreview` from the laptop, with key `~/.ssh/openreview_ed25519`, made for this host alone.
  - Václav first couldn't log in. His SSH agent offered too many keys ("Too many authentication failures"); `-o PubkeyAuthentication=no` got him to the password prompt.
- The **review** mesh: made by Václav on the laptop (`shrooms init --mesh review`, admin key `~/.config/shrooms/admin-review.json`).
  - Why its own mesh: the host runs hostile code; on the office mesh it would sit beside every machine.
  - The first attempt lost its passphrase. `shrooms mesh remove review`, then init again.
- shrooms installed on the host (`host/10-shrooms.sh`):
  - the published image under podman;
  - joined with a one-time invite, as device `openreview`, overlay `fddd:2d8f:96a1:4065:df41:eee8:6368:577a`;
  - credential until 2026-11-26: renew before then.
- The firewall needed shrooms' ports, 51820/udp (WireGuard), 60000/tcp and 9000/udp (delivery), and the mesh interface `shrooms0` allowed in. The same deny-by-default trap that hid the Duet's agent.
- Tunnel laptop ↔ openreview direct, about 35 ms.
- **Publishing (PoC):** reviews are served from this host, at http://77.237.236.27/.
  - Václav didn't want the review host pushing to data.vpavlin.xyz.
  - A pull from there was more than a PoC needs.
  - The cost: an escape lands next to the published reviews.
- **Web server:** Caddy, read-only, and a CSP with no scripts, frames, forms or outside resources (`host/20-web.sh`).
- **Anubis:** later, if traffic needs it, with `*.json` and `*.jsonl` exempt for tools.
- **HTTPS** needs a DNS name; ask Václav when wanted.
- **Agent (`host/30-agent.sh`):**
  - shrooms-agent runs as the unprivileged user `reviewer`, with lingering on, listening only on the review mesh address.
  - pi 1.4.0 on Node 22.
  - Venice: a key of its own for open review, with a spend limit. Václav typed it on this host; it lives in `/home/reviewer/.pi/agent/.env` (mode 600). `models.json` names it as `$VENICE_INFERENCE_KEY`.
  - First call through pi with `venice/deepseek-v4-1-flash-uncensored` answered.
  - Václav lost root SSH when password logins went off; he needs his public key added.

## 2026-10-27: the reviewer sandbox

- `sandbox/reviewer.Containerfile`: a self-contained image (`localhost/open-reviewer:latest`), built on the VPS with rootless podman. Contents:
  - build/read/run: git, node, pi 1.4.0, python, strace, ltrace;
  - static checks: semgrep, gitleaks, osv-scanner;
  - GUI run + record: Xvfb, xdotool, ffmpeg, ImageMagick, the Qt libraries;
  - faketime, for the clock shift.
- `sandbox/disguise.sh` (+ `profiles.json`): dress the sandbox as one of three real laptops (XPS 13 9340, ThinkPad X1 Carbon Gen 12, Framework 13 AMD), picked at random. A standard anti-evasion measure for a defensive reviewer; every review states the environment was instrumented. What works:
  - from inside the container: home dressing, child-process env (Wayland/GNOME/locale);
  - with the container launched `--hostname <x> --cap-add SYS_ADMIN`: hostname, DMI vendor/product bind-mounted over read-only sysfs, and `/run/.containerenv` masked with an empty bind-mount.
  - **Cannot hide:** the kernel version (the host's), so the host runs a stock Ubuntu kernel. Stated in every report.
- `sandbox/bait.sh`: plants fake secrets (SSH key, AWS creds, Solana seed, Electrum wallet) with unique canary strings, logged to bait.json so a read or an exfil of one is a red finding.
- `sandbox/record.sh`: strace across the process tree for file opens (and failures), connects and execs. Writes-outside-folder and the network capture are host-side (overlay diff, logging netns): next step.
- **Design note:** the module under test should run in a container the *pipeline* launches with these flags (hostname, caps, write-overlay, logging netns), driven by the reviewer pi session — not the shrooms cage, which does not expose them. The reviewer agent orchestrates; the pipeline runs the disguised sandbox.
- **Open for Václav:** his SSH public key (he lost root when password logins went off); his phone on the review mesh (one more invite) once there is a reviewer to talk to.
