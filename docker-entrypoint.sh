#!/usr/bin/env sh
set -eu

if [ "${1:-}" = "marker_private_web" ]; then
  exec marker_private_web --host "${HOST:-0.0.0.0}" --port "${PORT:-8765}"
fi

exec "$@"
