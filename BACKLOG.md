# Backlog

Beyond the working PoC (see NOTES.md). Ordered roughly by leverage.

## Make dynamic coverage complete
- **Software GL so Basecamp renders in the sandbox**, so pure-QML modules get real
  dynamic coverage (LIBGL_ALWAYS_SOFTWARE / mesa llvmpipe, or a virtual GPU). Build/
  install/hub code is already covered; QML-only is the gap the clean control surfaced.
- **Drive the module through Basecamp** (open it, use each feature) with screenshots and
  video, as the live-app testing playbook does.

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

## Harden
- Run the report-stage reviewer in a cage too (it reads untrusted evidence strings).
- Build-and-compare: build the module and check the artifact matches the submitted `.lgx`.
- TLS MITM in the sandbox sink (a sink CA in the image's trust store) so an exfil body,
  not just the hostname, is captured.

## Nicer live view
- A real stream (SSE/WebSocket) instead of meta-refresh, on its own relaxed-CSP path.

## Post-PoC (from the proposal)
- TEE models with response signatures; the runner in a confidential VM; review roots
  timestamped on the Logos chain; reports mirrored to Logos Storage; authenticated then
  rate-limited permissionless intake.
