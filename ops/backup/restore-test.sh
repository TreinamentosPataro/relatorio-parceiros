#!/bin/sh
set -eu

umask 077
restic --no-lock restore latest --tag partner-reports --target /restore
archive=/restore/work/database.dump
test -s "$archive"

pg_restore \
  --exit-on-error \
  --single-transaction \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname="$PGDATABASE" \
  "$archive"

schema_version_count=$(psql -X -Atqc 'SELECT count(*) FROM alembic_version')
source_count=$(find /restore/data/sources -type f 2>/dev/null | wc -l | tr -d ' ')
report_count=$(find /restore/data/reports -type f 2>/dev/null | wc -l | tr -d ' ')
test "$schema_version_count" = "1"

printf 'restore_status=verified source_objects=%s report_objects=%s\n' \
  "$source_count" "$report_count"
