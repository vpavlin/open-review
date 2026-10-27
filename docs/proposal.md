# Open review: automatic audits of Basecamp modules

Proposal · updated 2026-10-27 · laptop/shrooms for Václav

## Summary

A service that takes an open-source Basecamp module and publishes an adversarial review. The review covers:

- what the module reads, writes and contacts;
- whether it reaches for secrets;
- whether the published `.lgx` is what its source builds;
- whether it works, and how it breaks.

Every submission is tested properly: built, installed, clicked through, attacked and recorded. It runs in a sandbox dressed as an ordinary Linux laptop, so code that hides from sandboxes has a harder time hiding.

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

Each review is a folder at `data.vpavlin.xyz/reviews/<module>-<commit>/` for the PoC, later Logos Storage too. All public, since only open source is accepted.

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

## Plan

**PoC, on a dedicated VM, you as the only submitter:**

- [ ] The VM, from an image, with nothing else on it.
- [ ] The laptop disguise: three profiles, picked at random per run.
- [ ] The recording: strace, the write overlay, network and process logs, bait.
- [ ] A headless Basecamp in the sandbox, driven like our own app tests, with screenshots and video.
- [ ] The reviewer agent (pi, Venice DeepSeek uncensored) with the auditor's method, starting fresh per task.
- [ ] The publishing pipeline, with hash-chained, signed logs.
- [ ] Five real modules reviewed, one with a planted problem as a control. Measure cost and time.

**Lambda prize:** an open review service for Logos ecosystem software, with our PoC as the reference.
