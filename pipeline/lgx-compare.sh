#!/usr/bin/env bash
# lgx-compare <published.lgx> <rebuilt.lgx>: is the published package what its
# source builds? A package's manifest hashes each platform's files
# ("variants/linux-amd64") and all of them together ("root"). A release that
# merges builds from several machines (LNS: Linux from CI, macOS from a Mac)
# can't match a one-platform rebuild on "root", so each platform both have is
# compared on its own; the rest is said.
set -u
a=${1:?usage: lgx-compare <published.lgx> <rebuilt.lgx>}; b=${2:?}
ha=$(tar xzOf "$a" manifest.json | jq -c '.hashes // {}')
hb=$(tar xzOf "$b" manifest.json | jq -c '.hashes // {}')
echo "published: $(tar xzOf "$a" manifest.json | jq -r '"\(.name) \(.version)"')   rebuilt: $(tar xzOf "$b" manifest.json | jq -r '"\(.name) \(.version)"')"
same=0; diff=0
for k in $(jq -nr --argjson a "$ha" --argjson b "$hb" '($a|keys) as $x | ($b|keys) as $y | ($x - ($x - $y))[]' | grep '^variants/'); do
  va=$(jq -nr --argjson a "$ha" --arg k "$k" '$a[$k]'); vb=$(jq -nr --argjson b "$hb" --arg k "$k" '$b[$k]')
  if [ "$va" = "$vb" ]; then echo "SAME     $k  $va"; same=$((same+1)); else echo "DIFFERS  $k  published $va, rebuilt $vb"; diff=$((diff+1)); fi
done
only=$(jq -nr --argjson a "$ha" --argjson b "$hb" '($a|keys) - ($b|keys) | map(select(startswith("variants/"))) | join(" ")')
[ -n "$only" ] && echo "not rebuilt here: $only"
[ "$(jq -nr --argjson a "$ha" '$a.root')" = "$(jq -nr --argjson b "$hb" '$b.root')" ] && echo "SAME     root" || echo "root differs (expected if the published package merges other platforms)"
[ $same -gt 0 ] && [ $diff -eq 0 ] && exit 0 || exit 1
