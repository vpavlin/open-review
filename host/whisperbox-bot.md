# The WhisperBox submissions bot

Community submissions come in through a WhisperBox form; a headless
whisperbox_core 0.5.0 on the review host is the form's co-owner, reads the
answers, queues valid ones and replies to each submitter privately. Recipe
and design from atlas/whisperbox (2026-10-28): `whisperbox-bot-recipe.md`.

On the review host (all as the `reviewer` user, already done once):
- `~/wb-bot/dist`: whisperbox_core 0.5.0 (test build, feat/signed-answers
  37e9b48), loam_core 0.7.2, delivery_module 0.3.0, keycard 1.1.0, ble_mesh
  0.2.1, logosctl 0.3.1; checked against `SHA256SUMS`.
- logosctl unpacked in `/opt/logosctl`, linked from `/usr/local/bin`.
- `wb-bot.service` runs the node, `wb-bot-poll.service` runs
  `pipeline/whisperbox.py poll`. State in `~/wb-bot/state`: **back it up**,
  it holds the bot's identity; a new one means adding it as co-owner again.

## What Václav does, once

1. In WhisperBox, create the form (the JSON is in the recipe, §6).
2. Add the bot as co-owner. Its code (pubHex) is printed by
   `python3 ~/pipeline/whisperbox.py identity` on the review host:
   `03c09e3fcb03321c8067861e9504a89498f808f23a4da88881d1bd3b46e57ada89`.
3. Share the form's link with the review host:
   `python3 ~/pipeline/whisperbox.py join 'whisperbox://form?id=…&by=0x…'`.

From then on each valid answer is queued; the submitter gets a receipt, a
private "queued" reply with the live link, one when it starts, and one with
the report when it's done.

## Limits
- Signed answers need WhisperBox 0.5.0 on the submitter's side, not released
  yet. Answers from 0.4.2 arrive unsigned: their sender is unknown, so they
  share one small allowance (three waiting at a time).
- A signed submitter may have three reviews waiting. Identities are free, so
  this stops casual repeats, not a determined spammer.
- The free-text "note" is kept, never given to the reviewer: it would be a
  way to talk to the model.
