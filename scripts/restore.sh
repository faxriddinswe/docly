#!/bin/sh
# Restore a dump into a TARGET database (never the live one by accident).
# Usage: PGHOST=.. PGUSER=.. PGPASSWORD=.. scripts/restore.sh <dump-file> <target-db>
# The target db must not exist; it is created. Dropping/replacing the live DB is a manual, deliberate step (see RUNBOOK).
set -eu
[ $# -eq 2 ] || { echo "usage: $0 <dump-file> <new-db-name>" >&2; exit 2; }
createdb "$2"
pg_restore --no-owner --dbname="$2" "$1"
echo "restored $1 into database $2"
