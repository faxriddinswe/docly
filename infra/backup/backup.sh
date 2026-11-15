#!/bin/sh
# Nightly PostgreSQL backup. Usage: backup.sh once | backup.sh loop
# Env: PGHOST PGUSER PGPASSWORD PGDATABASE BACKUP_DIR(/backups) KEEP(7) BACKUP_HOUR(02)
set -eu
DIR="${BACKUP_DIR:-/backups}"
KEEP="${KEEP:-7}"

run_once() {
  mkdir -p "$DIR"
  f="$DIR/docly-$(date -u +%Y%m%d-%H%M%S).dump"
  # custom format: compressed, restorable selectively with pg_restore; written to a temp name first
  pg_dump --format=custom --no-owner --file="$f.tmp"
  mv "$f.tmp" "$f"
  # retention: keep the newest $KEEP dumps
  ls -1t "$DIR"/docly-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do rm -f "$old"; done
  echo "backup ok: $f ($(wc -c < "$f") bytes)"
}

case "${1:-once}" in
  once) run_once ;;
  loop)
    while true; do
      now=$(date -u +%s)
      next=$(date -u -d "$(date -u +%F) ${BACKUP_HOUR:-02}:00:00" +%s 2>/dev/null || echo $((now + 86400)))
      [ "$next" -le "$now" ] && next=$((next + 86400))
      sleep $((next - now))
      run_once || echo "backup FAILED" >&2
    done ;;
  *) echo "usage: $0 once|loop" >&2; exit 2 ;;
esac
