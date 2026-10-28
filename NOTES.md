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
- **Host:** a Contabo Cloud VPS 6 (6 vCPU, 12 GB, 200 GB), Ubuntu 24.04, kernel 6.8.0-147-generic, KVM guest, IP kept out of the public repo (see the private deploy note).
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
- **Publishing (PoC):** reviews are served from this host, at http://REVIEW-HOST/.
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
- Access: the laptop only, no user key, no phone on the mesh (decided 2026-10-27).

## 2026-10-27: trust-surface decisions (Václav)

- **No phone on the review mesh.** Václav talks to the reviewer through the laptop session (me); I task the reviewer over the mesh. One fewer device with access.
- **No SSH key for Václav on the host.** He reaches it via the laptop (me) or not at all. Only the laptop's `openreview_ed25519` key has shell access.
- So the review mesh has two devices: the laptop and the host. The laptop tasks the reviewer agent over the mesh; nothing else talks to it.

## 2026-10-27: first full PoC review — it works

- Full pipeline ran end to end on the `leaky-build` control (localdir): clone → static (gitleaks/osv/semgrep) → dynamic (disguised sandbox, DNS/connection sink, bait) → report (pi reviewer via logging gateway, live-streamed) → publish.
- **The dynamic stage caught the planted attack:** the module's `npm postinstall` read `/root/.ssh/id_ed25519`, `/root/.config/solana/id.json` and `/root/.aws/credentials`, then tried to reach `telemetry.handy-notes-cdn.net` (sinkholed + logged). `read_secret_then_contacted_external_host: true`.
- **The reviewer graded it right:** critical exfiltration (src/collect.js), the contradicted README "never leaves your device" claim, and it flagged the reviewer-directed comment (repo_tried_to_instruct_reviewer: true — a true positive on my control's own label).
- Published, served read-only: http://REVIEW-HOST/leaky-build-HEAD/ (and /live.html meta-refreshed during the run).
- **Fixes from the run:**
  - `analyse.py`: contacted-hosts parsing dropped the "dns … [sinkholed]" tag.
  - `report.sh`: the gateway now picks a free port and is waited-for-ready before pi launches; a stale gateway from the previous run had left the clean run's pi hanging with nowhere to call.
- **Model cost:** a few cents per review (gateway.jsonl has the token counts).
- **Next:** build-and-compare the submitted .lgx; harden (run report-pi in a cage too); the live view is meta-refresh (no JS) — a nicer stream later; a real community module end to end with Václav.

## 2026-10-27: clean control graded, and an honest gap surfaced

- `clean` (quiet_clock) run: behaviour correct — **no bait read, no hosts contacted**. The reviewer confirmed a genuine 5-line QtQuick clock.
- Notably the reviewer did NOT rubber-stamp it: it flagged **"high: dynamic run vacuous — LogosBasecamp never executed the module"**. True: the Basecamp AppImage aborts on GL/graphics in the headless sandbox, so for a **pure-QML module** the dynamic stage has little to show. For modules with build/install/hub code (the dangerous ones), dynamic capture is strong (leaky proved it).
- So: both controls graded right (known-bad critical, known-good clean), and the reviewer is appropriately skeptical of weak evidence.
- **Gap to close:** make Basecamp actually run a QML module in the sandbox (software GL: LIBGL_ALWAYS_SOFTWARE/mesa llvmpipe, or a virtual GPU), so QML-only modules get real dynamic coverage. Build+install code is already covered.
- PoC status: **working end to end** on both controls, published and served, live view during the run.

## 2026-10-27: the reviewer moves into the sandbox; forumer again

- Václav, on the first forumer report (6 findings, 57 lines): the auditor's
  reports are far more detailed and useful; "use the sandbox properly… a
  real-world review of the code and of the running things." Also: add usage
  stats; the screenshot was empty and the video didn't play.
- **Re-architected:** pi now runs *inside* the disguised sandbox
  (`review-in-sandbox.sh`, started by `reviewer.sh`), so it can build, run and
  attack the module itself. The Venice key stays on the host in `gateway.py`,
  which now demands a per-run random bearer token and is reached at
  `host.containers.internal`. The prompt follows the auditor's method and
  report shape (Bottom line / What I ran / FR-N with Exploit+Fix / What is
  solid / Not tested / Suggested order). `render.py` adds usage stats from
  `gateway.jsonl` and drops blank media with a note.
- **Image:** rebased on ubuntu:24.04, since Basecamp's AppImage needs glibc
  2.38+ and bookworm has 2.36. Mesa llvmpipe software GL renders (OpenGL 4.5
  under Xvfb). `libasound2` is `libasound2t64` there. cmake and ninja were
  missing, so forumer's C++ couldn't be built; added.
- **Gotcha:** `sudo -u reviewer -H podman …` sees a different (empty) podman
  store; use `sudo -iu reviewer`.
- **forumer run 2:** the reviewer compiled probes against forumer_core and ran
  them: wire/seal/base64/alias validation, then an ASan+UBSan fuzz probe into
  fromJson, sync::decode, openWire, sealed::open, vault::open. Slow: each probe
  recompiled the whole core with sanitizers on one core (~2.5 min per attempt,
  ~1 model call per 9 min). Prompt now says build the library once with all
  cores and link probes to it (63cc8ed).
- **No screen at all in run 2.** The in-sandbox reviewer was told to install
  the module into Basecamp but had no display, recorder or installer, so the
  report would have no media. Built `desk` (cdd7c83, acf36a7): a screen sized
  to the disguised panel, Basecamp extracted once with its own user dir, a
  whole-session recording, numbered shots, an lgpm-style `.lgx` install, and
  `desk read` (OCR with click points), since DeepSeek can't see images.
- Getting forumer to actually open took three fixes, each found by trying it:
  - forumer needs `delivery_module ~0.4.0`, which Basecamp doesn't bundle:
    a red cross in the sidebar. `fetch_deps.py` fetches declared deps from
    the official catalogue (the AppImage names it:
    logos-co/logos-modules-release logos-repo.json → index.json), on the
    host so the sandbox's hosts-contacted record stays the module's own,
    sha256-checked and cached.
  - tesseract read nothing from the inverted grey screen; 3× and
    contrast-stretched it reads every label but the smallest.
  - The window stayed 1600x900: xdotool's first match wasn't the visible one.
- Then: forumer opens to its identity screen at 1920x1200, its node joins
  logos.dev, and it **sends on /forumer/3/public/proto before any identity
  exists**, for the reviewer to look at. The 72 s video plays.
- forumer's README says the code is on `hardening/v0.2.5`, not master. Not
  so: master is the v0.2.5 tag plus two docs-only commits.
- `review.sh` took an `.lgx` URL and ignored it; it now fetches it.
- A hard time cap (REVIEW_MAX_MIN, default 150), shown in the report when hit.
- **Venice outage, 17:38 UTC:** `deepseek-v4-1-flash-uncensored` answered
  `500 Inference processing failed` to every request, tiny or large, while
  its siblings answered on the same key; listed online, DIEM left (0.59 of 2
  used, $0 USD). The auditor on proteus hit it too. pi gave up on the first
  500 and run 2 published as if done, with no report.
  - Fixed: the gateway retries 5xx/429 for ~25 min, then marks the run; a
    run with that mark or no report is published as **failed**, not a
    verdict either way (eece930, b905fa5). Both agents moved to
    `deepseek-v4-1-flash-1017` (Václav's choice); `REVIEW_MODEL` sets it.
- **The gateway never logged a reply.** pi streams; the gateway parsed the
  body as one JSON document and logged `{}`: no replies, no usage, $0 in
  the report. It now reassembles the stream (03aff47). Run 2 used 57 calls
  but only ~10 min of model time in 2 h: the rest was compiling probes.
- **Re-runs overwrote the published folder,** so run 2 showed run 1's
  report. A re-run now moves the last one aside (7fc6f01).
- **Run 3** started 17:48 UTC with the v0.2.5 `.lgx`, its dependencies,
  desk, and the 1017 model.

## 2026-10-28: forumer run 4, the first auditor-grade report

- Run 3 ended when the reviewer's `pkill -9 -f 'desk read'` matched pi
  (whose argv was the whole prompt); `pkill ffmpeg` had ended the video.
  Fixed: a one-line pi argument, OCR at 2x on one thread (3 s, not
  minutes), the recorder renamed, kill-by-PID in the prompt (374a09e).
- Run 4 (19:33 UTC, deepseek-v4-1-flash-1017, the v0.2.5 `.lgx`): 33
  screenshots through identity, recovery phrase, private forums, posting,
  settings, alias attacks, backup/restore, wrong password and images; a
  38 MB recording; 8 probes; 163/163 core tests under ASan/UBSan.
- It hit the 150-minute cap with **no report written**, and then hung all
  night: `strace -f` waits for Basecamp/Xvfb/the recorder that pi started.
  Fixed: wait on pi's `timeout`, then end what's left; and a reviewer that
  stops without a report is resumed once to write it up (0a6daa6). For run 4
  I resumed it by hand: a 239-line report.
- **The report:** all six sections, 19 findings (1 High, 4 Medium, 14
  Low), 22 `[run]` and 11 `[read]` tags. Top: signed posts can fill peers'
  disks (preview blobs with no budget or runtime pruning); private-forum
  metadata (forum id, persona key, reply graph) stored in clear; unsigned
  messages grow maps unbounded; holder hints make the node dial
  attacker-chosen addresses incl. loopback/LAN. Run 1, for comparison: 6
  findings in 57 lines.
- **Usage:** 200 calls, 42.8 M input tokens (41.3 M cached), 105 k output,
  33 min of model time, **$0.90**, 2 retries, 0 provider failures.
- Published: /forumer-b9907523bffc/ (the earlier attempts beside it).

## 2026-10-28: a spend cap, open-review reviews itself, root taken away

- **agentic-job (cgwalters)** compared: different job (safe agents on your
  own repo vs. evidence about a third-party module), but worth learning
  from: probes of its own hardening, per-run spend caps at a broker, a key
  off the box, blunt limits. Adopted: the self-check, the cap, root taken
  away, and (ours) a recording proxy. Key off the box: post-PoC.
- **1 DIEM per review** (Václav). The gateway prices each reply, refuses the
  review's token past 0.8 and a write-up token past 1.0, serves only the
  review's model. The report shows Venice's real charge (balance before and
  after, whole account) beside the computed one, and where the spend went.
  Compaction left off: its summary calls are uncached and cost more.
- **open-review on itself** (6c46c82): 16 findings in 14 min for 0.208 DIEM
  (computed 0.205). Critical: the host-side renderer followed symlinks out
  of the run dir, so a module could have published the Venice key; no
  published review contained it; fixed with dir-fd walking, O_NOFOLLOW,
  regular files only. Also fixed: shell injection from URLs, the model not
  pinned at the gateway, a 40-min outer timeout that did nothing (bash as
  PID 1 ignores TERM), the DNS sink not wired in since the move, raw-IP
  connects unreported, desk path traversal, a malformed report.json
  stopping publication (32537c1).
- **Root taken away** (d80d804): pi and the module run as `pavel` (uid
  1000, no sudo); root keeps the disguise, bait, DNS sink, strace, screen,
  recorder and a transparent mitmproxy that the user's 80/443 is redirected
  to. 20 self-checks. The leaky control, reviewed for real at a 0.15 cap:
  Critical, and the proxy recorded the POST of all three bait files to
  example.com/ingest; 0.058 DIEM.
- Gotchas: my own `pkill -f` and `pgrep -f` matched the shells running them
  (twice); a backstop sleep held review.sh's pipe open; a `grep -c` with no
  match ended an `&&` chain before an edit, which looked applied.
