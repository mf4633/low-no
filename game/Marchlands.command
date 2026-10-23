#!/usr/bin/env sh
#  Marchlands, without building anything -- macOS and Linux.
#  Double-click it, or run ./Marchlands.command from a terminal.
cd "$(dirname "$0")" || exit 1
for PY in python3 python; do
  command -v "$PY" >/dev/null 2>&1 && exec "$PY" -m marchlands --web "$@"
done
echo "Marchlands needs Python 3.9 or newer. https://www.python.org/downloads/"
exit 1
