#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ -f .local/database.json ]]; then
  pg_bin=/usr/local/opt/postgresql@17/bin
  if ! "$pg_bin/pg_ctl" -D "$PWD/.local/postgres" status >/dev/null 2>&1; then
    "$pg_bin/pg_ctl" -D "$PWD/.local/postgres" -l "$PWD/.local/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $PWD/.local/pgsocket" -w start
  fi
fi
