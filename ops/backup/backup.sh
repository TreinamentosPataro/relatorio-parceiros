#!/bin/sh
set -eu

umask 077
archive=/work/database.dump
trap 'rm -f "$archive"' EXIT HUP INT TERM

pg_dump --format=custom --file="$archive"
if ! restic cat config >/dev/null 2>&1; then
    printf '%s\n' 'backup_status=repository_unavailable' >&2
    exit 1
fi
restic backup --tag partner-reports "$archive" /data/sources /data/reports
restic forget --tag partner-reports --keep-within 30d --prune
restic check --read-data-subset=5%

printf '%s\n' 'backup_status=verified'
