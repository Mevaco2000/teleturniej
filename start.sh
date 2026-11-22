#!/bin/sh
# Uruchamia serwer gry. Przy pierwszym starcie przygotowuje środowisko Pythona.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Przygotowuję środowisko, to potrwa chwilę..."
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
exec .venv/bin/python -m server "$@"
