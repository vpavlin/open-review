# The review host, from nothing

On a fresh Ubuntu 24.04 VM (Contabo Cloud VPS 6 for the PoC), as root, from a
clone of this repository:

    git clone https://github.com/vpavlin/open-review /opt/open-review
    cd /opt/open-review/host
    bash 00-base.sh        # updated, named, SSH by key only, deny-by-default firewall
    bash 10-shrooms.sh     # shrooms (pinned commit and image); join the review mesh by hand
    bash 20-web.sh         # Caddy serving /srv/reviews, read-only, strict CSP
    bash 30-agent.sh       # shrooms-agent (pinned image) and pi 1.4.0 for the reviewer user
    bash 40-pipeline.sh    # the pipeline, Basecamp 0.3.2 by hash, the pinned sandbox
                           # image, the queue, the intake session
    bash 45-whisperbox.sh <bot build>   # optional: WhisperBox submissions

40 ends with what is left by hand: the model key, typed on the host, and
joining the mesh with an invite from its admin.

**Deploying a change** is `git pull` in /opt/open-review and `bash
host/40-pipeline.sh` again. Each review records the pipeline commit it ran.

**Proof:** `host/test/vm.sh up && host/test/vm.sh setup && host/test/vm.sh
verify` does all of the above on a throwaway local VM and runs a review of
the leaky control with a stand-in for the model (no key, no budget). On
2026-10-28 it passed from a clean VM: 31 of 31 self-checks, the reviewer
and the record out of the module's reach, the module's exfiltration
recorded, the report published. Getting there found five faults a rebuild
would have hit, all fixed.

**Pinned:** shrooms' installers by commit and its images by digest; pi,
Node, semgrep, mitmproxy, gitleaks and osv-scanner by version; the sandbox's
base image by digest and its Ubuntu packages from a dated archive snapshot;
Basecamp's AppImage by URL and sha256. Not pinned: the host's own Ubuntu
packages (00-base upgrades them), and what a reviewed module pulls in.

**Known:** a host whose address is in 10.0.2.0/24 collides with rootless
podman's user-mode network (the sandbox can't reach the gateway; its
self-check refuses the review).
