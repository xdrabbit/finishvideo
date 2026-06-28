#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 DIR" >&2
  exit 2
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg not found on PATH" >&2
  exit 1
fi

out_dir=$1
mkdir -p "$out_dir"

make_clip() {
  local color=$1
  local frequency=$2
  local output=$3

  ffmpeg -hide_banner -y \
    -f lavfi -i "color=c=${color}:s=320x180:r=30:d=2" \
    -f lavfi -i "sine=frequency=${frequency}:sample_rate=48000:d=2" \
    -c:v libx264 -pix_fmt yuv420p \
    -c:a aac -b:a 96k \
    -shortest \
    "$out_dir/$output"
}

make_clip red 440 clip1.mp4
make_clip green 554 clip2.mp4
make_clip blue 659 clip3.mp4

ffmpeg -hide_banner -y \
  -f lavfi -i "sine=frequency=220:sample_rate=48000:d=8" \
  -c:a aac -b:a 128k \
  "$out_dir/music.m4a"

echo "Created smoke fixtures in $out_dir"
