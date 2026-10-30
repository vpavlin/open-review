# Focus: peer to peer

The module as a participant in a network of strangers. Cover every item in
/run/inventory.json: the files that send, receive, parse, verify, store or
sync what peers send, and every method the module exposes.

For each, ask what a hostile peer can do with it:
- **Every message type** it accepts: how it is parsed, which fields are
  checked, what is verified (signatures, senders, timestamps) and when
  (before or after it is stored, acted on, relayed).
- **Resources:** what one peer can make it store, send, compute or relay;
  amplification (a small message causing large work or traffic); per-sender
  limits; growth over time.
- **Sync and ordering:** catch-up, reconciliation, clocks, duplicates,
  replays, forks, a peer lying about time or history.
- **Privacy on the wire:** what a passive observer learns (topics, sizes,
  timing, identities, linkability), what the relay/store nodes see.
- **Identity:** spoofing, squatting, impersonation, what binds a message to
  its author.

Write probes that act as the hostile peer: craft the frames and feed them to
the module's own parsing and handling code.
