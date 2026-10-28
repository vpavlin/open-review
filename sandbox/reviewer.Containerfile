# The reviewer's sandbox: where a submitted Basecamp module is built, installed,
# run, recorded and attacked. Self-contained (does not depend on the shrooms
# workbench image), so open-review stands on its own.
#
# Root inside, nothing of the host's: the agent runs each review as a fresh
# caged pi session (shrooms ADR-072), with no credentials and a network limited
# to the model gateway and package mirrors.

# Pinned so the image rebuilt elsewhere is this one: the base by digest, Ubuntu's
# packages from a dated snapshot of the archive (apt 2.7+), the rest by version.
FROM docker.io/library/ubuntu:24.04@sha256:24737cef17f4e22b1977df7d9a05e77c4e28b7da5b8911f8d8ccda136bf3573c AS reviewer
ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_SNAPSHOT=20261028T000000Z
# The snapshot service is https only, and the base image has no CA
# certificates: those come from the live archive first (found rebuilding the
# host on a fresh VM, 2026-10-28), then every package after from the snapshot.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
    && echo "APT::Snapshot \"${UBUNTU_SNAPSHOT}\";" > /etc/apt/apt.conf.d/50snapshot
# Node 22 (the AppImage needs a newer glibc than Debian bookworm shipped).
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs=22.23.4-1nodesource1 \
    && rm -rf /var/lib/apt/lists/*

# Build, read and run tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates openssh-client build-essential pkg-config cmake ninja-build \
        python3 python3-pip python3-venv pipx \
        ripgrep jq less procps psmisc unzip xz-utils file \
        strace ltrace \
    && rm -rf /var/lib/apt/lists/*

# pi 1.4.0 and the exact tree of its dependencies (pi-shrinkwrap.json, taken
# from the image that worked): pinning pi alone left npm to resolve the rest
# anew, and on 2026-10-28 a fresh build failed on @aws-sdk/core@^3.978.7,
# published minutes before. Its tarball is checked against the registry's
# sha512.
COPY pi-shrinkwrap.json /tmp/pi-shrinkwrap.json
RUN set -eux; cd /opt; \
    npm pack -q @earendil-works/pi-coding-agent@1.4.0 >/dev/null; \
    test "sha512-$(openssl dgst -sha512 -binary earendil-works-pi-coding-agent-1.4.0.tgz | base64 -w0)" = \
         "sha512-Z41LpZ3yYHSC/UUps6Mr39UMFPwH8elhJBG9DY1P7kuzsE5qSK/6eMj2EHzO5evJRQWLbKSqUMw+4nCNtIyiQg=="; \
    tar xzf earendil-works-pi-coding-agent-1.4.0.tgz && mv package pi && rm earendil-works-pi-coding-agent-1.4.0.tgz; \
    cd pi && jq 'del(.devDependencies)' package.json > p.json && mv p.json package.json; \
    cp /tmp/pi-shrinkwrap.json npm-shrinkwrap.json && npm ci --omit=dev --no-audit --no-fund; \
    chmod +x dist/bundle/cli.js && ln -sf /opt/pi/dist/bundle/cli.js /usr/local/bin/pi; \
    npm cache clean --force; pi --version

# Run and record a GUI (Basecamp is Qt): an X server to drive, ffmpeg and
# ImageMagick to record, and the libraries Qt apps load. AppImages self-extract
# (no FUSE in a cage).
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb xauth xdotool x11-utils x11-xserver-utils imagemagick ffmpeg tesseract-ocr \
        fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji \
        libgl1 libegl1 libopengl0 libglib2.0-0 libfontconfig1 libfreetype6 libdbus-1-3 libnss3 libasound2t64 \
        libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 \
        libx11-xcb1 libxrender1 libxi6 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libsm6 libice6 \
        libgl1-mesa-dri libglx-mesa0 libglu1-mesa mesa-utils fuse3 \
    && rm -rf /var/lib/apt/lists/*
# Software GL, so Qt/Basecamp render with no GPU; a Qt software fallback too.
ENV APPIMAGE_EXTRACT_AND_RUN=1 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QUICK_BACKEND=software QTWEBENGINE_DISABLE_SANDBOX=1

# Static review checks: secrets, dependency vulnerabilities, code patterns.
# gitleaks and osv-scanner as pinned release binaries; semgrep via pipx.
ARG GITLEAKS=8.21.2
ARG OSV=1.9.0
RUN set -eux; a="$(dpkg --print-architecture)"; \
    case "$a" in amd64) gl=x64; os=linux_amd64;; arm64) gl=arm64; os=linux_arm64;; esac; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS}/gitleaks_${GITLEAKS}_linux_${gl}.tar.gz" | tar -xz -C /usr/local/bin gitleaks; \
    curl -fsSL "https://github.com/google/osv-scanner/releases/download/v${OSV}/osv-scanner_${os}" -o /usr/local/bin/osv-scanner; \
    chmod +x /usr/local/bin/osv-scanner
RUN PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install semgrep==1.182.1 >/dev/null

# faketime, to move the sandbox clock forward during a run so code that waits
# before misbehaving still acts.
RUN apt-get update && apt-get install -y --no-install-recommends faketime && rm -rf /var/lib/apt/lists/*

# What Basecamp modules build against, so a review doesn't spend its time on
# apt: forumer's fourth run installed Qt and libsodium itself, 11 minutes of a
# 150-minute review.
RUN apt-get update && apt-get install -y --no-install-recommends \
        qt6-base-dev qt6-declarative-dev qt6-remoteobjects-dev \
        libsodium-dev libsqlite3-dev nlohmann-json3-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# The recording proxy, and the firewall that sends the user's web traffic to
# it; both root's, out of the user's reach.
RUN apt-get update && apt-get install -y --no-install-recommends iptables \
    && rm -rf /var/lib/apt/lists/*
RUN PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install mitmproxy==12.3.1 >/dev/null

# The reviewer and the module run as an ordinary user, with no sudo: root in
# the sandbox keeps the instruments (after agentic-job: take root away). Named
# like a person, uid 1000 like a laptop's first user; Ubuntu's stock user goes.
RUN userdel -r ubuntu 2>/dev/null; useradd -m -u 1000 -s /bin/bash pavel

# The reviewer is a second account (a second person on the laptop, to the
# module's eye). It runs things as pavel, the module's user, through a broker
# root runs (pipeline/module_broker.py), not sudo: setuid does nothing under
# strace. pavel can do nothing as it, so what the module runs can't touch the
# reviewer's report or probes (open-review's own review, FR-2/FR-14).
RUN useradd -m -u 1001 -s /bin/bash ondra && chmod 750 /home/pavel /home/ondra

COPY disguise.sh bait.sh record.sh profiles.json /usr/local/sbin/
RUN chmod +x /usr/local/sbin/disguise.sh /usr/local/sbin/bait.sh /usr/local/sbin/record.sh

LABEL xyz.vpavlin.open-review="reviewer"
CMD ["sleep", "infinity"]
