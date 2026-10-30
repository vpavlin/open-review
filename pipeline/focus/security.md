# Focus: security

The whole module as an attacker sees it. Cover every item in
/run/inventory.json: every source file in the module's folders, every method
it exposes, its build.

For each, ask what reaches it from outside and what an attacker gains:
- **Untrusted input:** peers' messages, other modules calling its methods,
  files it loads, the UI. Parsing, bounds, types, recursion, sizes.
- **Keys and crypto:** where keys are made, kept, used, shown, exported; what
  is signed and what is checked; nonces, randomness, comparisons.
- **Authorisation:** who may do what, and where that is checked; what another
  module installed beside it in Basecamp can call.
- **State and storage:** what it writes, where, how it reads it back, what a
  corrupted or hostile file does.
- **Build and supply chain:** what the build fetches and runs, pins, CI.

Run Basecamp with the module enough to confirm what you found in code and to
see what it sends; the UI is not this focus's main subject.
