#!/usr/bin/env bash
set -euo pipefail

transition="fade"
duration="0.5"
bpm=""
beat_sync="false"

args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --transition)
      transition="$2"; shift 2 ;;
    --duration)
      duration="$2"; shift 2 ;;
    --bpm)
      bpm="$2"; shift 2 ;;
    --beat-sync)
      beat_sync="true"; shift ;;
    *)
      args+=("$1"); shift ;;
  esac
done

if [ "${#args[@]}" -lt 3 ]; then
  echo "Usage: finishvideo [--transition fade] [--duration 0.5] [--beat-sync --bpm 124] clip1.mp4 clip2.mp4 ... output.mp4"
  exit 1
fi

last_index=$((${#args[@]} - 1))
output="${args[$last_index]}"
unset "args[$last_index]"

clips=("${args[@]}")

durations=()
for clip in "${clips[@]}"; do
  d=$(ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$clip")
  durations+=("$d")
done

inputs=()
for clip in "${clips[@]}"; do
  inputs+=("-i" "$clip")
done

filter=""
prev="[0:v]"
sum="${durations[0]}"

for ((i=1; i<${#clips[@]}; i++)); do
  offset=$(awk "BEGIN { print $sum - $duration * $i }")

  if [[ "$beat_sync" == "true" && -n "$bpm" ]]; then
    offset=$(awk "BEGIN {
      beat = 60 / $bpm;
      print int(($offset / beat) + 0.5) * beat
    }")
  fi

  out="[v$i]"
  filter+="${prev}[$i:v]xfade=transition=${transition}:duration=${duration}:offset=${offset}${out};"

  prev="$out"
  sum=$(awk "BEGIN { print $sum + ${durations[$i]} }")
done

filter="${filter%;}"

ffmpeg -hide_banner -y \
  "${inputs[@]}" \
  -filter_complex "$filter" \
  -map "$prev" \
  -pix_fmt yuv420p \
  -c:v hevc_videotoolbox -b:v 8000k \
  -an \
  "$output"

echo "Created $output"
