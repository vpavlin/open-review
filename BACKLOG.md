# Backlog

Beyond the working PoC (see NOTES.md). Ordered roughly by leverage. Done since
the first version: software GL and driving the module in Basecamp (desk), the
reviewer inside the sandbox, the recording HTTPS proxy, a per-review spend cap,
the sandbox self-check, the reviewer and module without root.

## From open-review's own review (6c46c82, 2026-10-28)
Fixed: FR-1, FR-3, FR-4, FR-5, FR-6, FR-8, FR-9, and FR-2 in part (the module
can no longer touch the behaviour record, the logs or the video). Still open:
- **FR-2/FR-14, the rest: the reviewer and the module are one user.** What the
  reviewer builds and runs, the module included, can rewrite the reviewer's
  draft report, its probes and its screenshots, and can read pi's tokens (the
  gateway's cap holds). Next: run untrusted code as a second user (`desk`
  starts Basecamp as it; builds and probes through a helper), and the
  write-up pass in a fresh sandbox that gets the session, not the old one.
- **FR-7:** a repository can configure its own scanners (`.semgrepignore`,
  `.gitleaks.toml`) to hide findings, and a scanner that fails is silent. Run
  them with our config only, and record failures.
- **FR-11:** caret ranges are wrong for 0.x versions in fetch_deps.py.
- **FR-12:** gateway DoS surface (unbounded body size, threads) and secret
  redaction that misses some key shapes.
- **FR-13:** the image and host are not pinned (apt, pipx, npm at latest);
  record the image digest per review at least.
- **FR-15:** reviews are plain HTTP and the hash chain is unsigned.
- **FR-16:** anything staged in the run's evidence/media dirs is published
  same-origin; publish a fixed list of file types only.

## Community submissions through WhisperBox (atlas/whisperbox, 2026-10-28)
- **Phase 1, a form:** Václav creates a WhisperBox form; an always-on
  headless `whisperbox_core` under logosctl on the review host is made its
  co-owner (`addCoOwner`), reads answers with `getDecryptedResponses`,
  validates them (repo URL, 40-hex commit, optional .lgx URL), queues them,
  and replies privately to the submitter (`replyToResponse`: "queued #N",
  then the report link), with receipts on (`setAutoReceipts`). Its own
  WHISPERBOX_CORE_DATA, HOME and LOGOSCTL_CONFIG_DIR; arguments with `str:`;
  recipe in WhisperBox's docs/BUILD.md (review-2026-10-22 branch).
- **Needs WhisperBox 0.5.0** (signed answers; built, not released): 0.4.2
  doesn't sign answers on open forms, so a submitter's identity can't be
  trusted for per-submitter limits. Open forms are Sybil-cheap; real limits
  need an address list or, later, token gating.
- **Phase 2, votes: not in WhisperBox.** Answers are sealed to the owner, so
  no one else can verify a tally. Public signed votes: a small LEZ program
  (LNS holdings are on LEZ; one vote per account, a public tally), or a
  dedicated app. Linking a WhisperBox address to a LEZ account needs a proof
  that doesn't exist yet (LEZ keys don't sign messages).
- Under RLN, every reply costs the bot's node message budget.

## Learnt from cgwalters-forge/agentic-job
- **Throwaway model keys:** a per-review key minted by a broker off this box,
  revoked at the end (post-PoC; the key on the review VM is fine for now).
- **Who may trigger a review:** with permissionless intake, anyone can drain
  the shared budget; per-submitter limits before anything runs.
- **Pin what runs** (FR-13 above), and attest it.

## Spend
- 1 DIEM a review is the cap. Reading the code was 31% of forumer run 5's
  1.20 DIEM; the prompt now asks for targeted reads. Measure again, then cut
  what costs most for least.
- Publish gateway.jsonl compressed: every request carries the whole
  conversation, 256 MB for forumer run 5.

## Tie into the Basecamp module security plan
These wire open-reviewer's output into the ecosystem plan (integrity manifests, the
Freeze rule, Evaluated Releases catalog, advisories).
- **`lgx verify` + rootHash/signature as a first-class signal.** Each review emits the
  integrity-manifest fields directly: `.lgx` rootHash and per-platform SHA-256, signer
  DID, whether it is signed / unsigned / a new signer. Low effort, high leverage for the
  Freeze rule and the Evaluated Releases catalog.
- **"Evaluated rootHash X on date Y against criteria Z" as the report headline**, never
  "approved/safe", plus a machine-readable advisory entry (a known-bad rootHash record)
  the pipeline can emit, to feed a public advisories list.
- **Build-and-compare:** build the module and check the artifact matches the
  submitted `.lgx` (needs Nix in the sandbox, or the module's own build).

## Nicer live view
- A real stream (SSE/WebSocket) instead of meta-refresh, on its own relaxed-CSP path.

## Post-PoC (from the proposal)
- TEE models with response signatures; the runner in a confidential VM; review roots
  timestamped on the Logos chain; reports mirrored to Logos Storage; authenticated then
  rate-limited permissionless intake.
