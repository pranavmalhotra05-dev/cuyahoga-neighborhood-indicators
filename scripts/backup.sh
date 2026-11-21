#!/usr/bin/env bash
# Back up the database, SQL files and source manifest, or restore from a backup.
#   bash scripts/backup.sh                             create backups/cuyahoga_YYYYMMDD_HHMMSS.tar.gz
#   bash scripts/backup.sh --restore ARCHIVE           restore to a scratch folder and verify hashes
#   bash scripts/backup.sh --restore ARCHIVE --force   also copy the restored files over the live ones
# Environment: KEEP=7 number of newest backups to keep; PYTHON python executable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP="${KEEP:-7}"
BACKUPS="$ROOT/backups"
MANIFEST_NAME="SHA256SUMS.txt"

usage() { sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

RESTORE=""; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --restore) [ $# -ge 2 ] || { echo "--restore needs an archive path" >&2; exit 2; }; RESTORE="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else echo "python not found; set PYTHON" >&2; exit 3; fi
fi
if command -v sha256sum >/dev/null 2>&1; then SHA() { sha256sum "$@"; }
elif command -v shasum >/dev/null 2>&1; then SHA() { shasum -a 256 "$@"; }
else echo "sha256sum or shasum is required" >&2; exit 3; fi

log() { printf '%s [backup] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
now_ms() { date +%s%3N; }
secs() { awk -v m="$1" 'BEGIN { printf "%.2f s", m / 1000 }'; }

list_archive() {  # print member names of an archive
  case "$1" in
    *.tar.gz) tar -tzf "$1" ;;
    *.zip) "$PY" -I -c "import sys,zipfile; print('\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))" "$1" ;;
    *) echo "unsupported archive type: $1" >&2; return 1 ;;
  esac
}
extract_archive() {  # extract archive $1 into directory $2
  case "$1" in
    *.tar.gz) tar -xzf "$1" -C "$2" ;;
    *.zip) "$PY" -I -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$1" "$2" ;;
  esac
}
verify_dir() {  # verify the hashes listed in the manifest inside directory $1
  ( cd "$1" && SHA -c "$MANIFEST_NAME" )
}

if [ -n "$RESTORE" ]; then
  [ -f "$RESTORE" ] || { echo "archive not found: $RESTORE" >&2; exit 1; }
  RESTORE="$(cd "$(dirname "$RESTORE")" && pwd)/$(basename "$RESTORE")"
  t0="$(now_ms)"
  SCRATCH="$BACKUPS/restore_scratch_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$SCRATCH"
  log "restoring $RESTORE to scratch folder $SCRATCH"
  extract_archive "$RESTORE" "$SCRATCH"
  verify_dir "$SCRATCH"
  log "hashes verified"
  "$PY" -I -c "
import sys, duckdb
con = duckdb.connect(sys.argv[1], read_only=True)
n = con.execute('SELECT count(*) FROM fact_acs').fetchone()[0]
print('restored database opens; fact_acs rows:', n)
" "$SCRATCH/data/cuyahoga.duckdb"
  if [ "$FORCE" = "1" ]; then
    log "--force given: copying restored files over the live project files"
    if [ -f "$ROOT/data/cuyahoga.duckdb" ]; then
      cp "$ROOT/data/cuyahoga.duckdb" "$ROOT/data/cuyahoga.duckdb.before_restore"
      log "previous live database saved as data/cuyahoga.duckdb.before_restore"
    fi
    rm -f "$ROOT/data/cuyahoga.duckdb.wal"
    mkdir -p "$ROOT/data" "$ROOT/sql"
    cp "$SCRATCH/data/cuyahoga.duckdb" "$ROOT/data/cuyahoga.duckdb"
    cp "$SCRATCH/data/source_manifest.csv" "$ROOT/data/source_manifest.csv"
    cp "$SCRATCH"/sql/*.sql "$ROOT/sql/"
    rm -rf "$SCRATCH"
    log "live files replaced"
  else
    log "live database NOT modified (use --force to replace it). Scratch copy kept at $SCRATCH"
  fi
  log "restore finished in $(secs $(( $(now_ms) - t0 )))"
  exit 0
fi

# ---- create a backup ----
t0="$(now_ms)"
DB="$ROOT/data/cuyahoga.duckdb"
[ -f "$DB" ] || { echo "database not found: $DB" >&2; exit 1; }
mkdir -p "$BACKUPS"

log "checkpointing $DB"
if ! "$PY" -I -c "import sys, duckdb; c = duckdb.connect(sys.argv[1]); c.execute('CHECKPOINT'); c.close()" "$DB" 2>/dev/null; then
  if [ -f "$DB.wal" ]; then
    echo "cannot checkpoint (database in use?) and a WAL file exists; close other users of the database and retry" >&2
    exit 1
  fi
  log "WARNING: checkpoint not possible (database in use) but no WAL file exists, continuing"
fi
[ ! -f "$DB.wal" ] || { echo "WAL file still present after checkpoint" >&2; exit 1; }

STAMP="$(date +%Y%m%d_%H%M%S)"
STAGE="$(mktemp -d "$BACKUPS/.stage_XXXXXX")"
VERIFY=""
trap 'rm -rf "$STAGE" "$VERIFY"' EXIT
mkdir -p "$STAGE/data" "$STAGE/sql"
cp "$DB" "$STAGE/data/cuyahoga.duckdb"
cp "$ROOT/data/source_manifest.csv" "$STAGE/data/source_manifest.csv"
cp "$ROOT"/sql/*.sql "$STAGE/sql/"
( cd "$STAGE" && SHA data/cuyahoga.duckdb data/source_manifest.csv sql/*.sql > "$MANIFEST_NAME" )
log "manifest has $(wc -l < "$STAGE/$MANIFEST_NAME" | tr -d ' ') entries"

if command -v tar >/dev/null 2>&1; then
  ARCHIVE="$BACKUPS/cuyahoga_${STAMP}.tar.gz"
  tar -czf "$ARCHIVE" -C "$STAGE" data sql "$MANIFEST_NAME"
else
  ARCHIVE="$BACKUPS/cuyahoga_${STAMP}.zip"
  "$PY" -I -c "
import sys, zipfile
from pathlib import Path
stage, out = Path(sys.argv[1]), sys.argv[2]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(stage).as_posix())
" "$STAGE" "$ARCHIVE"
fi
log "archive written: $ARCHIVE"

# verify: list the archive, extract to a temp folder, re-hash
MEMBERS="$(list_archive "$ARCHIVE")"
for need in "$MANIFEST_NAME" data/cuyahoga.duckdb data/source_manifest.csv; do
  echo "$MEMBERS" | grep -qx "$need" || { echo "verification failed: $need missing from archive" >&2; exit 1; }
done
log "archive lists $(echo "$MEMBERS" | grep -vc '/$') files"
VERIFY="$(mktemp -d "$BACKUPS/.verify_XXXXXX")"
extract_archive "$ARCHIVE" "$VERIFY"
verify_dir "$VERIFY" >/dev/null
log "re-hash of the extracted archive matches the manifest"

# retention: keep the newest KEEP archives (timestamped names sort chronologically)
mapfile -t ALL < <(ls -1 "$BACKUPS" | grep -E '^cuyahoga_[0-9]{8}_[0-9]{6}\.(tar\.gz|zip)$' | sort)
total="${#ALL[@]}"
if [ "$total" -gt "$KEEP" ]; then
  for f in "${ALL[@]:0:$((total - KEEP))}"; do
    rm -f "$BACKUPS/$f"
    log "removed old backup $f"
  done
fi

size="$(wc -c < "$ARCHIVE" | tr -d ' ')"
present="$(ls -1 "$BACKUPS" | grep -cE '^cuyahoga_[0-9]{8}_[0-9]{6}\.(tar\.gz|zip)$')"
log "done: $ARCHIVE ($size bytes) in $(secs $(( $(now_ms) - t0 ))); keeping newest $KEEP, $present present"
