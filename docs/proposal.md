# Open review: automatic audits of Basecamp modules

Updated 2026-10-28 · laptop/shrooms for Václav

**Code:** [github.com/vpavlin/open-review](https://github.com/vpavlin/open-review) (public). **Status: working proof of concept** — the full pipeline runs end to end on a dedicated VM. See `NOTES.md` (running log) and `BACKLOG.md` in the repo.

## Summary

A service that takes an open-source Basecamp module and publishes an adversarial review. The review covers:

- what the module reads, writes and contacts;
- whether it reaches for secrets;
- whether the published `.lgx` is what its source builds;
- whether it works, and how it breaks.

Every submission is tested properly: built, installed, clicked through, attacked and recorded. It runs in a sandbox dressed as an ordinary Linux laptop, so code that hides from sandboxes has a harder time hiding.

**It works today.** The PoC was graded on two controls: a planted supply-chain sample was caught as critical (its install read the bait SSH key, Solana seed and AWS creds and tried to phone home), and a clean module came back clean. Both are published, read-only, with full evidence and a live view that refreshes while a review runs.

- **Scope:** Basecamp modules only for now. LEZ programs, APKs and other software later.
- **What it is:** evidence and findings. It never certifies a module as safe.
- **Model:** Venice DeepSeek V4.1 Flash, uncensored variant, behind the gateway. The reviewer never holds the key. Compute is the main cost, so a Venice partnership matters.
- **Each review starts from nothing:** a fresh conversation, an emptied folder and a new sandbox (ADR-072).
- **Everything is public:** the report, the behaviour record, screenshots and video, the session log, and the gateway's log of every model request.

## How a review runs

1. **Submit.** A repository URL and commit, plus the module's `.lgx` if one is published.
    - **PoC:** a task you send from the Shrooms Agents app to the reviewer session, marked fresh.
    - **Later:** a Basecamp app, with submissions signed by the submitter's key and sent over Logos Messaging, or a WhisperBox form.
2. **Queue.** One review at a time per reviewer.
3. **Fresh sandbox.** It's dressed as a laptop (see below), with no credentials. Its network allows only the model gateway, package mirrors and whatever the module itself contacts, and all of that is recorded.
4. **Review.** The base review below, within a token and time budget.
5. **Report.** The agent writes it to its outbox, the only way out of the sandbox.
6. **Publish.** A plain program, not the model, checks the report against a schema and publishes it with the logs and recordings.

## The base review: every submission

1. **Dependencies:** what's pulled in, pinned or not, known vulnerabilities, install scripts, binary blobs in the repo, CI workflows that leak secrets.
2. **Build from source,** and compare the result with the submitted `.lgx`. A binary its source doesn't build is the first finding.
3. **Read the code like an auditor:** where it touches files, keys, the network, other modules, the user's data, and Keycard or wallet signing.
4. **Install and test it properly** in a headless Basecamp, the way we test our own apps:
    - open it and use every feature;
    - take screenshots along the way and record the whole session as video;
    - feed it malformed input, a hostile peer and oversized messages;
    - write and run a proof of concept for each finding.
5. **Uninstall it,** and record what stays behind.
6. **Other modules it calls** are listed with their review status. An unreviewed one becomes a possible follow-up task, not part of this review.
7. **Write the report and the behaviour label:** findings with severity, file and line, evidence and the proof of concept's output, plus what was checked and found clean. A finding without evidence is marked unconfirmed.

## What is recorded during the run

- **Reads:** every file opened, and every failed attempt. A module trying `~/.ssh` and being refused is often the most telling line. Recorded with `strace` across every process the module starts.
- **Writes:** Basecamp's data folder and the home directory are layered over a throwaway copy, so afterwards we get an exact list of what was created, changed or deleted. Anything outside the module's own folder is flagged.
- **Network:** every connection and DNS lookup.
- **Processes:** everything started. A module that quietly starts a blockchain node is a finding.
- **Resources:** CPU, memory and disk over time.
- **Bait:** fake secrets planted around the home directory: an SSH key, a wallet seed, Keycard answers, unique tokens. Reading one, or a token turning up in network traffic, is a red finding: "it read your fake seed phrase and sent it to x.y.z".

The behaviour label is the short version of this record: domains contacted, files touched outside its folder, processes started, bait touched. It's meant to sit next to Install in Basecamp's package manager later.

## A sandbox that looks like a laptop

Malicious code often checks whether it's being watched, and behaves until it isn't. Each run picks one real model at random and dresses the sandbox as it:

| Model | Example values |
| --- | --- |
| Dell XPS 13 9340 | Intel Core Ultra 7 155H, 16 GB, 1920×1200 |
| Lenovo ThinkPad X1 Carbon Gen 12 | Intel Core Ultra 7 165U, 32 GB, 1920×1200 |
| Framework Laptop 13 (AMD) | Ryzen 7 7840U, 32 GB, 2256×1504 |

| What it checks | A default container shows | What we show |
| --- | --- | --- |
| Hardware model (`/sys/class/dmi/id/*`) | the host's, or nothing | the chosen model's |
| Container markers (`/.dockerenv`, `/run/.containerenv`, cgroup paths) | present | hidden |
| Process 1 | a shell or the app | systemd, with the usual user services |
| Hostname, username | random hex, `root` | ordinary names, like `pavel-xps` |
| Environment | `container=podman`, sometimes `CI=true` | a desktop session's: Wayland, `DESKTOP_SESSION`, locale |
| CPU, memory, battery, network card | the host's, or gaps | the model's, with a battery that discharges and a vendor network card address |
| Lived-in signs | seconds of uptime, empty home | days of uptime, documents, a browser profile with history, shell history, other apps |
| Display, input | none, or 1024×768 | the model's panel resolution, mouse movement while testing |

Two more tricks against code that waits:

- **Shift the clock:** move it forward hours and days during the run.
- **Run longer:** keep the module running longer than a quick check would.

**The limits:**

- **The kernel version shows,** since a container shares the host's kernel. The host should run a kernel that looks like an ordinary desktop distribution's.
- **gVisor is easy to detect,** which pulls against using it for isolation. For the PoC: a disguised container, discarded after every run, inside a dedicated VM.
- **Determined code can always find a tell.** So the recording and the bait carry the evidence. Code that notices the sandbox and goes quiet shows up as "did nothing suspicious here", never as "safe".

## Threat model

- **Steal something:** there's nothing to steal. The sandbox holds only bait, and the model key stays in the gateway.
- **Escape the sandbox:** the sandbox is a container inside a dedicated VM with nothing else in it. An escape reaches a VM that holds no keys and is rebuilt from an image.
- **Wreck it:** CPU, memory and time are capped, and the sandbox is discarded after each run.
- **Instruct the model** ("ignore your instructions", "this module is safe"): it can't publish, since only the pipeline does. Against biased wording:
    - the recorded behaviour and bait results go into the report whatever the model writes;
    - findings need a reproducible proof of concept;
    - the agent reports any instruction it finds in the repository, as a finding in its own right;
    - the published logs show what the model saw.
- **Poison later reviews:** there's no memory between reviews and no shared folder.

## What gets published

Each review is a public folder on the review VM, `http://REVIEW-HOST/<module>-<commit>/` for the PoC (the review node never writes to anyone else's storage), later Logos Storage too. All public, since only open source is accepted. A re-review of the same commit keeps the earlier one beside it.

| File | What it is |
| --- | --- |
| `report.md`, `report.json` | findings, evidence, what was checked |
| `label.json` | the behaviour label |
| `behaviour/` | reads, writes (the write diff), network, processes, resources, bait hits |
| `media/` | screenshots and the video of the test session |
| `session.jsonl` | the agent's whole session: every tool call and its output |
| `gateway.jsonl` | every model request and reply, with token counts |
| `meta.json` | repository, commit, artifact hashes, laptop profile used, model, prompt and image versions |

**Trust in the PoC:** the logs are hash-chained and signed with a key the review host holds, so any edit after publishing shows. The inputs are pinned, so anyone can re-run a review and compare.

**After the PoC:**

- Venice's TEE models with response signatures: tested 2026-10-27; the hardware attestation works, the signature chain doesn't yet close.
- The runner in a confidential VM.
- Review roots timestamped on the Logos chain.
- TLSNotary spot proofs.
- The live public view of a running review.

## Who may submit, and cost

1. **PoC:** you only.
2. **Authenticated:** a list of keys, with Lambda entrants added when they enter.
3. **Permissionless:** anyone, with a rate limit per key and per repository, a queue and a cost cap.

Proper testing costs more than reading code. Estimates on Venice DeepSeek V4.1 Flash ($0.33 per million tokens in, $1.32 out) are $2–8 per module, depending on size. The PoC measures this from the gateway log. Each run has a hard token and time cap, and a run that hits one reports what it covered.

## Deeper reviews, on request

- **Called modules:** review the modules it calls, if they haven't been reviewed.
- **A second model:** another model on the code, with disagreements flagged.
- **Fixes:** offered as pull requests to the author.
- **Release watching:** each new version reviewed and compared with the last, with an alert over Logos Messaging when behaviour changes.

## How this fits the Basecamp module security plan

open-review is the **automated triage** layer of the broader plan to make community
Basecamp modules safe to build, submit, review and run. It does not replace the trust
architecture (provenance-bound privileges, signer continuity, access-policy-on,
per-module OS sandboxing) — those are platform changes in Basecamp. It observes and
reports; it never approves.

| Plan item | What open-review does |
| --- | --- |
| Automated triage (isolated runner: verify, hash match, native-binary inventory, dep & secret scans, sandboxed run with net/file tracing, AI review) | This, end to end. Reports as signals, never "passed review". |
| Reviewer runbook (fresh VM, no org tokens, read-only agent creds, testnet only, read scripts first) | Enforced mechanically: fresh sandbox per submission, the model key held off the sandbox in a gateway, bait instead of real keys. |
| Reviewer-targeting / prompt injection | The repo is hostile data; only the pipeline publishes; findings need a reproducible PoC; text in the repo aimed at the reviewer is itself a finding. |
| Integrity manifest + Freeze rule | meta.json records commit, artifact hashes, model/prompt versions; logs are hash-chained — the evaluated-rootHash record. |
| Risk tiers | The tiered depth (base testing for all, deeper on request/paid) maps to Tier 0/1/2; bait-and-exfil detection matters most at Tier 2 (keys/funds). |
| Negligent builder (most common) | Static scans + "read your key, phoned home" catch plaintext keys, leaked secrets and abandoned deps cheaply, at scale. |

**The honest ceiling:** a reviewer cannot catch a dormant or remotely-configured payload,
and cannot confine native code that runs unreviewed. The OS sandbox and provenance-bound
privileges (the plan's high-value R&D) are what limit damage there. open-review makes the
cheap attacks expensive to hide and produces the evaluated-rootHash record the Freeze rule
and an Evaluated Releases catalog need.

## Status

**PoC, on a dedicated VM (Contabo VPS 6), administered only over a private mesh, its reviews public over HTTP — done:**

- [x] The VM, rebuildable from `host/00-base.sh` → `10-shrooms.sh` → `20-web.sh` → `30-agent.sh`.
- [x] The laptop disguise: three profiles (XPS 13, ThinkPad X1, Framework 13), picked at random per run.
- [x] The recording: strace (reads, incl. refused; writes; connects; execs), a logging DNS/connection sink, bait.
- [x] The reviewer agent (pi, Venice DeepSeek uncensored), auditor's method, fresh per task; the model key held off the sandbox in a logging gateway.
- [x] The publishing pipeline: hash-chained logs, an escaped read-only report, and a live view.
- [x] Graded on a known-bad (critical) and a known-good (clean) control.

**Next (see `BACKLOG.md`):** software GL so Basecamp renders pure-QML modules in the sandbox; build-and-compare the `.lgx`; `lgx verify` + rootHash/signature as a first-class signal; harden the report stage.

**Lambda prize:** an open review service for Logos ecosystem software, with this PoC as the reference.
