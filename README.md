# open-review

Automatic, adversarial reviews of Basecamp modules: built, installed, tested,
attacked and recorded in a sandbox dressed as an ordinary Linux laptop, with
everything published (report, behaviour record, screenshots and video, the
agent's session log and every model request).

- `docs/proposal.md`: what it is and why (also at data.vpavlin.xyz).
- `NOTES.md`: what was done, when, and why: the running log.
- `host/`: the review host's setup, as scripts, in order. The host can be
  rebuilt from these.

Status: proof of concept, one reviewer, one submitter (Václav).

## A note on `test-modules/`

`test-modules/leaky-build/` is a **defensive control sample**: a module whose
`npm postinstall` reads planted *fake* secrets and tries to POST them to a
non-existent host. It exists so the reviewer's detection can be graded against a
known answer. It is harmless (the target does not resolve, the secrets are bait),
clearly labelled, and not for any other use. `clean/` is the known-good control.

