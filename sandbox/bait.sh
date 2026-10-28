#!/usr/bin/env bash
# Plant fake secrets around the home directory with unique canary strings, so a
# read of one, or a canary appearing in the module's network traffic, is a red
# finding: "it read your fake seed phrase and sent it to x.y.z". Nothing here
# is real; the canaries are logged so the recorder can match them.
set -uo pipefail
h=${1:-/home/pavel}; OUT=${2:-/tmp/bait.json}
canary() { echo "CANARY-$(head -c9 /dev/urandom | base64 | tr -dc a-zA-Z0-9 | head -c12)"; }
declare -A B
mkdir -p "$h/.ssh" "$h/.aws" "$h/.config/solana" "$h/.electrum"

c=$(canary); B["$h/.ssh/id_ed25519"]=$c
printf -- '-----BEGIN OPENSSH PRIVATE KEY-----\n%s\nfake-key-for-bait-%s\n-----END OPENSSH PRIVATE KEY-----\n' "$c" "$c" > "$h/.ssh/id_ed25519"
chmod 600 "$h/.ssh/id_ed25519"

c=$(canary); B["$h/.aws/credentials"]=$c
printf '[default]\naws_access_key_id=AKIA%s\naws_secret_access_key=%s\n' "${c:7:16}" "$c" > "$h/.aws/credentials"

c=$(canary); B["$h/.config/solana/id.json"]=$c
printf 'seed phrase: witch collapse practice feed shame %s open despair creek road again ice\n' "$c" > "$h/.config/solana/id.json"

c=$(canary); B["$h/.electrum/wallet"]=$c
printf 'xprv-fake-%s\n' "$c" > "$h/.electrum/wallet"

# The user's, as on a laptop: the module runs as that user and can read them.
chown -R pavel:pavel "$h/.ssh" "$h/.aws" "$h/.config" "$h/.electrum" 2>/dev/null
{ echo "{"; first=1; for p in "${!B[@]}"; do [ $first = 1 ] || echo ","; first=0; printf '  "%s": "%s"' "$p" "${B[$p]}"; done; echo; echo "}"; } > "$OUT"
echo "bait: planted ${#B[@]} (canaries in $OUT)"
