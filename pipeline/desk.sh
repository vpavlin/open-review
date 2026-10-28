#!/usr/bin/env bash
# desk: the reviewer's desktop inside the sandbox. A screen the size of the
# disguised laptop's panel, Basecamp on it, a recorder for the whole session,
# and a text view of the screen, since the review model cannot see images.
#
#   desk start                 screen + recorder + Basecamp (empty user dir)
#   desk install <file.lgx>    install a module the way lgpm does, restart Basecamp
#   desk restart               restart Basecamp (same user dir)
#   desk read                  the words on screen, with the x,y to click them
#   desk click <x> <y>         left click
#   desk click-text <text>     click the first on-screen word/phrase matching text
#   desk type <text>           type text into the focused field
#   desk key <keys>            xdotool key names, e.g. Return, ctrl+k, Escape
#   desk shot <name>           screenshot to /run/media/NN-<name>.png
#   desk log [n]               the last n lines of Basecamp's log (default 40)
#   desk stop                  stop Basecamp and finalise the video
#   desk time                  how much of the review's time is used and left
#
# Screenshots and the video are published with the report; take a shot at
# every step that shows something, named for what it shows.
set -uo pipefail
S=/run/desk; M=/run/media; U=/root/.local/share/Logos/LogosBasecamp
mkdir -p "$S" "$M"
export DISPLAY=:99 QT_QPA_PLATFORM=xcb WAYLAND_DISPLAY= QT_FORCE_STDERR_LOGGING=1
res=$(jq -r '.resolution // .res // empty' /run/behaviour/disguise.json 2>/dev/null); res=${res:-1920x1200}
W=${res%x*}; H=${res#*x}

bc_up() {
  [ -d /opt/bc/squashfs-root ] || { mkdir -p /opt/bc && cd /opt/bc && /opt/basecamp/Basecamp.AppImage --appimage-extract >/dev/null 2>&1; cd - >/dev/null; }
  mkdir -p "$U/modules" "$U/plugins"
  ( cd /root && exec /opt/bc/squashfs-root/AppRun --user-dir "$U" >>"$M/basecamp.log" 2>&1 ) &
  echo $! > "$S/bc.pid"
  # Basecamp is up when its window is mapped; give its modules a moment more.
  for _ in $(seq 1 90); do xdotool search --onlyvisible --name Basecamp >/dev/null 2>&1 && break; sleep 1; done
  sleep 8
  # Fill the laptop's panel; Basecamp opens at 1600x900. There is no window
  # manager, so only the visible window takes the size.
  for wid in $(xdotool search --onlyvisible --name Basecamp 2>/dev/null); do
    xdotool windowmove "$wid" 0 0 windowsize "$wid" "$W" "$H" 2>/dev/null
  done
  sleep 1
}
bc_down() {
  [ -f "$S/bc.pid" ] || return 0
  pkill -TERM -f '/opt/bc/squashfs-root' 2>/dev/null; sleep 3
  pkill -KILL -f '/opt/bc/squashfs-root' 2>/dev/null; rm -f "$S/bc.pid"
}
install_one() {  # unpack one .lgx the way lgpm does
  local lgx=$1 t name type dest
  t=$(mktemp -d)
  tar xzf "$lgx" -C "$t" || { echo "desk: $lgx is not an lgx (gzip tar)"; rm -rf "$t"; return 1; }
  name=$(jq -r .name "$t/manifest.json"); type=$(jq -r .type "$t/manifest.json")
  # The manifest is the module's: a name like "../../x" made rm -rf and the
  # copy land outside the plugins folder (FR-8, 2026-10-28).
  [[ "$name" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$ && "$name" != *..* ]] || { echo "desk: refusing module name \"$name\""; rm -rf "$t"; return 1; }
  case "$type" in ui_qml|ui) dest="$U/plugins/$name";; *) dest="$U/modules/$name";; esac
  [ -d "$t/variants/linux-amd64" ] || { echo "desk: no linux-amd64 variant in $lgx"; rm -rf "$t"; return 1; }
  rm -rf "$dest"; mkdir -p "$dest"
  cp -a "$t/variants/linux-amd64/." "$dest/"; cp "$t/manifest.json" "$dest/"
  [ -d "$t/assets" ] && cp -an "$t/assets/." "$dest/" 2>/dev/null
  echo linux-amd64 > "$dest/variant"
  echo "desk: installed $name ($type) $(jq -r .version "$t/manifest.json"), sha256 $(sha256sum "$lgx" | cut -c1-16)…"
  rm -rf "$t"
}
clock() {  # time and budget used and left, from the limits the sandbox and gateway set
  python3 - <<'PY' 2>/dev/null
import json
try:
    d=json.load(open("/run/logs/spend.json"))
    s,t=d["spent"],d["testing"]
    print(f"[budget] {s:.2f} of {t:.2f} DIEM for testing used" + ("; STOP TESTING and write the report now" if s>=0.85*t else ""))
except Exception: pass
PY
  read -r t0 max < /run/logs/clock 2>/dev/null || return 0
  used=$(( ($(date +%s)-t0)/60 )); left=$(( max-used )); by=$(( max-40 ))
  if [ "$used" -ge "$by" ]; then
    echo "[clock] ${used} of ${max} min used, ${left} left: STOP TESTING and write the report now"
  else
    echo "[clock] ${used} of ${max} min used, ${left} left; start the report by minute ${by}"
  fi
}
nextshot() { n=$(ls "$M"/*.png 2>/dev/null | wc -l); printf '%02d' $((n+1)); }
ocr() {  # one line per text line on screen: "x,y  text" (x,y = its centre)
  f="$S/ocr.png"
  ffmpeg -loglevel error -y -f x11grab -video_size "${W}x${H}" -i :99 -frames:v 1 "$f" || return 1
  # Basecamp is light text on dark. Inverted grey alone gives tesseract
  # nothing at all (tried 2026-10-27); tripled and contrast-stretched it reads
  # every label but the smallest.
  # Doubled reads as many words as tripled in half the time, and one thread
  # beats six: beside a compile, threaded tesseract took minutes, the
  # reviewer started killing it, and its pkill took pi down (forumer, run 3).
  convert "$f" -alpha off -colorspace Gray -negate -resize 200% -depth 8 -level 10%,80% "$S/ocr2.png" 2>/dev/null || cp "$f" "$S/ocr2.png"
  OMP_THREAD_LIMIT=1 timeout 60 tesseract "$S/ocr2.png" - --psm 11 tsv 2>/dev/null | awk -F'\t' 'NR>1 && $12!="" && $11>40 {
      k=$3"-"$4"-"$5; if(!(k in t)){t[k]=$12; l[k]=$7; tp[k]=$8; r[k]=$7+$9; b[k]=$8+$10; o[++n]=k}
      else {t[k]=t[k]" "$12; if($7+$9>r[k])r[k]=$7+$9; if($8+$10>b[k])b[k]=$8+$10}
    } END {for(i=1;i<=n;i++){k=o[i]; printf "%d,%d\t%s\n", (l[k]+r[k])/4, (tp[k]+b[k])/4, t[k]}}'
}

[ "${1:-}" != time ] && clock
case "${1:-}" in
  time) clock ;;
  start)
    Xvfb :99 -screen 0 "${res}x24" -nolisten tcp >/dev/null 2>&1 & echo $! > "$S/xvfb.pid"; sleep 2
    # The recorder runs under its own name: a reviewer clearing stuck
    # processes with "pkill ffmpeg" ended run 3's video.
    cp -f "$(command -v ffmpeg)" "$S/desk-recorder"
    "$S/desk-recorder" -nostdin -loglevel error -f x11grab -framerate 4 -video_size "${W}x${H}" -i :99 \
      -c:v libx264 -preset veryfast -crf 32 -pix_fmt yuv420p -movflags +faststart "$M/session.mp4" \
      >/dev/null 2>"$S/ffmpeg.err" & echo $! > "$S/ffmpeg.pid"
    bc_up; echo "desk: ${res} screen, Basecamp up, recording to media/session.mp4"; ocr | head -40 ;;
  install)
    lgx=${2:?desk install <file.lgx>}
    bc_down
    # Its dependencies first, as Basecamp's own install does; the pipeline
    # fetched them from the official catalogue into /run/lgx/deps.
    for d in /run/lgx/deps/*.lgx; do
      [ -f "$d" ] || continue
      n=$(tar xzOf "$d" manifest.json 2>/dev/null | jq -r .name)
      if [ -d "/opt/bc/squashfs-root/usr/modules/$n" ] || [ -d "/opt/bc/squashfs-root/usr/plugins/$n" ]; then
        echo "desk: $n is bundled with Basecamp"; continue
      fi
      install_one "$d"
    done
    install_one "$lgx" || exit 1
    bc_up; ocr | head -40 ;;
  restart) bc_down; bc_up; ocr | head -40 ;;
  read) ocr ;;
  click) xdotool mousemove "$2" "$3" click 1; sleep 1.5 ;;
  click-text)
    want=${2:?desk click-text <text>}
    hit=$(ocr | awk -F'\t' -v w="$want" 'BEGIN{w=tolower(w)} index(tolower($2),w){print $1; exit}')
    [ -n "$hit" ] || { echo "desk: \"$want\" not on screen"; exit 1; }
    xdotool mousemove "${hit%,*}" "${hit#*,}" click 1; sleep 1.5; echo "desk: clicked \"$want\" at $hit" ;;
  type) xdotool type --delay 40 -- "$2"; sleep 0.5 ;;
  key) shift; xdotool key "$@"; sleep 1 ;;
  shot)
    f="$M/$(nextshot)-${2:-screen}.png"
    ffmpeg -loglevel error -y -f x11grab -video_size "${W}x${H}" -i :99 -frames:v 1 "$f" && echo "desk: $f" ;;
  log) tail -n "${2:-40}" "$M/basecamp.log" ;;
  stop)
    bc_down
    if [ -f "$S/ffmpeg.pid" ]; then
      p=$(cat "$S/ffmpeg.pid"); kill -INT "$p" 2>/dev/null
      # ffmpeg writes the index on SIGINT; killed harder, the mp4 won't play.
      for _ in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
      kill -9 "$p" 2>/dev/null; rm -f "$S/ffmpeg.pid"
    fi
    [ -f "$S/xvfb.pid" ] && kill "$(cat "$S/xvfb.pid")" 2>/dev/null; rm -f "$S/xvfb.pid"
    echo "desk: stopped" ;;
  *) sed -n '2,20p' "$0" ;;
esac
