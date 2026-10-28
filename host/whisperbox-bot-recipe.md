# WhisperBox submissions bot: headless whisperbox_core 0.5.0 (linux-amd64)

For the open-review intake (phase 1): an always-on headless WhisperBox node that is a CO-OWNER of
the submission form. It reads and decrypts the answers, validates them, queues reviews, sends
receipts, and replies privately to each submitter.

Not a public release: whisperbox_core 0.5.0 is built from vpavlin/whisperbox-logos branch
`feat/signed-answers` (every answer signed, ADR 0019).

## Files

| File | What |
|---|---|
| `whisperbox_core-0.5.0.lgx` | the core, linux-amd64 portable |
| `logos-loam_core-module.lgx` | loam_core 0.7.2 (the transport) |
| `logos-delivery_module-module.lgx` | delivery_module 0.3.0 (Logos Delivery) |
| `logos-keycard-module.lgx` | keycard 1.1.0 (loam_core needs it loaded) |
| `logos-ble_mesh-module.lgx` | ble_mesh 0.2.1 (loam_core depends on it; idle without Bluetooth) |
| `logosctl-x86_64.AppImage` | logosctl 0.3.1 (logos-co/logos-logoscore-cli), the headless runtime |
| `SHA256SUMS` | checksums |

The four dependencies are the versions on the Basecamp 0.3 LAN repo on 2026-10-28.

## 1. Install on Ubuntu 24.04 (no Basecamp, no GUI)

```sh
sudo apt-get install -y libgl1 libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3   # Qt offscreen deps
mkdir -p /opt/logosctl && cd /opt/logosctl
cp ~/wb-bot/logosctl-x86_64.AppImage . && chmod +x logosctl-x86_64.AppImage
./logosctl-x86_64.AppImage --appimage-extract >/dev/null   # no FUSE needed
ln -sf /opt/logosctl/squashfs-root/usr/bin/logosctl /usr/local/bin/logosctl
logosctl --version        # 0.3.1, commit 4d47b0ee
```

(If the extracted binary misses a library, `ldd squashfs-root/usr/bin/logosctl | grep "not found"` names it.)

## 2. One session for the bot

Everything the node keeps is in one directory. All three variables are needed:
- `HOME`: the bundled storage_module writes `~/.logos_storage`;
- `LOGOSCTL_CONFIG_DIR`: the daemon, the installed modules, the logs;
- `WHISPERBOX_CORE_DATA`: the identity and the event log. Without it the core uses the account's
  REAL home (getpwuid), so any other WhisperBox session on the account would share the identity.

```sh
S=/srv/wb-bot
mkdir -p $S/home/.whisperbox-core
cat > $S/env <<EOF
export HOME=$S/home WHISPERBOX_CORE_DATA=$S/home/.whisperbox-core LOGOSCTL_CONFIG_DIR=$S/cfg QT_QPA_PLATFORM=offscreen
EOF
. $S/env
logosctl daemon start --detach
for f in ~/wb-bot/*.lgx; do logosctl install "$f" -y; done
logosctl module load whisperbox_core            # loads loam_core, keycard, delivery_module, ble_mesh
logosctl module ls                              # whisperbox_core 0.5.0, loam_core 0.7.2, ... "loaded"
```

Always-on: run `logosctl daemon start` (foreground, without `--detach`) from a systemd unit with the
same three variables and `Restart=always`, plus a one-shot `ExecStartPost` that runs the `install`
and `module load` lines (`install` of an already-installed package is a no-op).

## 3. The bot's identity, for addCoOwner

```sh
logosctl call whisperbox_core snapshot -j | tail -1
```

The result is a JSON string. Read `identity.pubHex` (66 hex characters, starts with 02 or 03): that's
the co-owner code. `identity.address` is the bot's address. `nodeReady: true` means it's connected (it
takes 10 to 60 s after load).

The identity is created on first start and kept in `$WHISPERBOX_CORE_DATA` (mode 0600). Back up that
directory: a new identity means a new co-owner code, and the form owner must add it again.

## 4. Václav adds the bot (on his own device)

1. Create the form (see section 6).
2. In WhisperBox: open the form, then Co-owners, paste the bot's `pubHex`. From a headless creator
   this is `addCoOwner str:<formId> str:<pubHex>`.
3. Give the bot the form's share link (`whisperbox://form?id=…&by=0x…`; the "Share" button, or
   `shareUri str:<formId>`).

## 5. The bot's calls

Prefix every argument with `str:`: a bare `1` or `true` arrives as a number or a bool and the method
gets nothing useful. Wrap each call in `timeout 30`. The last line of `-j` output is
`{"result": "<JSON string>"}`; parse it twice.

```sh
F='whisperbox://form?id=<id>&by=0x<creator>'      # the share link
ID=<form id>

logosctl call whisperbox_core joinForm "str:$F"              # once; pins the creator
logosctl call whisperbox_core getDecryptedResponses "str:$ID"
#  -> {"responses":[{"respondent":"0x…","submittedAt":ms,"answers":[{"questionId":"repo","value":"https://…"},…],
#        "confirmationId":"…","verified":true,"timeVerified":true,"receivedAt":ms,"confirmed":false,"replies":0},…]}
logosctl call whisperbox_core confirmResponse "str:$ID" "str:<respondent address>"   # a receipt for one answer
logosctl call whisperbox_core replyToResponse "str:$ID" "str:<confirmationId>" "str:queued, #3"
logosctl call whisperbox_core setAutoReceipts "str:$ID" str:true                     # alternative: receipt for everything
logosctl watch whisperbox_core --event stateChanged          # optional: wake on new data instead of polling
```

Meaning of the fields:
- **`verified`**: `true` means the answer is signed by the `respondent` it names. Use only those
  for per-submitter limits. `false` means unsigned: sent by an older WhisperBox, or by someone
  claiming another address. It counts towards nothing; show it, don't trust its respondent.
- **`timeVerified` / `receivedAt`**: the Logos Delivery network time of the earliest copy seen.
- **receipts:**
  - `confirmResponse` takes the respondent ADDRESS, `replyToResponse` the confirmationId.
  - Prefer confirming after validation: `setAutoReceipts` would also confirm junk.
  - A receipt is public but unlinkable to the answer; the submitter sees "received".
- **replies:** they are sealed to a one-off key in the answer. Only the submitter's WhisperBox shows
  them. Answers from older WhisperBox versions can't be replied to; the error says so.

Keep the bot's own record of which `confirmationId`s it has queued or replied to. The core doesn't
dedupe for you: a second `replyToResponse` sends a second reply.

## 6. Form shape

Title "Submit a Basecamp module for open-review", not anonymous, no address list, edits off,
`showResponseCount` on (submitters see the count).

```json
{"title":"Submit a Basecamp module for open-review",
 "description":"An automatic adversarial review of a Basecamp module, published at http://77.237.236.27/. One repository + commit per answer. You get a receipt, then a private reply with your queue number and later the report link.",
 "showResponseCount":true,
 "questions":[
  {"id":"repo","type":"shortText","text":"Repository URL (https://github.com/owner/name)","required":true},
  {"id":"commit","type":"shortText","text":"Commit (40-character SHA)","required":true},
  {"id":"lgx","type":"shortText","text":"Published .lgx URL (optional: review the package you ship, too)","required":false},
  {"id":"module","type":"shortText","text":"Module name, if the repo has several (optional)","required":false},
  {"id":"note","type":"textarea","text":"Anything the reviewer should know (optional)","required":false}
 ]}
```

Validate on the bot. WhisperBox checks only "required" and the type:
- `repo` matches `^https://(github\.com|gitlab\.com|codeberg\.org)/[\w.-]+/[\w.-]+/?$`;
- `commit` matches `^[0-9a-f]{40}$` and exists in the repo;
- `lgx` is http(s), with a size cap.

## 7. Limits to know

- **Respondents need WhisperBox 0.5.0 for signed answers**, and 0.5.0 isn't released to users yet.
  Until it is, answers from the public 0.4.2 arrive `verified:false`: treat their `respondent` as
  unauthenticated. Receipts and replies still work for them (0.4.2 answers carry a reply key); only
  much older versions answer "can't receive replies".
- **Identities are free**, so per-submitter limits stop casual repeats, not someone who makes new
  identities.
- **RLN:** today the node sends with RLN off. When the network turns RLN on, every receipt and reply
  needs the node's RLN membership, from a budget shared with all its traffic. Budget a few messages
  per submission.
- **Back up `$WHISPERBOX_CORE_DATA`.** It holds the identity and the decrypted log.
