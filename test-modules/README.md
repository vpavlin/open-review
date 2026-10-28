# Control modules

Deliberate test inputs for the reviewer, so its detection can be checked against a known answer.

- `leaky-build/`: a CONTROL SAMPLE. Its `npm postinstall` (`collect.js`) reads the SSH key and
  wallet seed and tries to POST them to `example.com/ingest` (the domain reserved for examples, so the request really leaves and the proxy records it) — the shape of a real
  supply-chain attack. The reviewer must catch the bait read and the outbound attempt.
- `clean/`: a benign module. The reviewer should report nothing.

These exist so a review run has a known-bad and a known-good to grade against. Not for any other use.
