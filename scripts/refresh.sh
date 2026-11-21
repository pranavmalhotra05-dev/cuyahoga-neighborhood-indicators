#!/usr/bin/env bash
# Run the whole pipeline end to end: download, ingest, build DB, quality checks,
# spatial checks, geocoding, maps, web export, analysis.
# Usage: bash scripts/refresh.sh [--from STEP] [--help]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# number|name|script|kind   (kind: required = missing file is an error, optional = skipped with a message)
STEPS=(
  "0|download|src/00_download.py|required"
  "1|ingest|src/01_ingest.py|required"
  "2|build|src/02_build_db.py|required"
  "3|checks|src/03_checks.py|required"
  "4|spatial|src/04_spatial_checks.py|optional"
  "5|geocode|src/05_geocode.py|optional"
  "6|maps|src/06_maps.py|optional"
  "7|web|src/07_export_web.py|required"
  "9|analysis|src/09_analysis.py|optional"
)

usage() {
  cat <<USAGE
Usage: bash scripts/refresh.sh [--from STEP] [--help]

Runs the pipeline from the project root, whatever the current directory is.

Steps (number, name, script):
USAGE
  local s
  for s in "${STEPS[@]}"; do
    IFS='|' read -r n name script kind <<<"$s"
    printf '  %s  %-9s %s (%s)\n' "$n" "$name" "$script" "$kind"
  done
  cat <<USAGE

Options:
  --from STEP   start at STEP (a number or a name from the list above); earlier steps are skipped.
  --help        show this help.

Environment:
  SKIP_GEOCODE=1    do not call the network geocoder; reuse data/geocode_results.csv.
  SKIP_DOWNLOAD=1   skip step 0 (files already present are never downloaded again anyway).
  PYTHON            python executable to use (default: python3, then python).

Output: logs/refresh_YYYYMMDD_HHMMSS.log, with a timestamp on every line.
Exit codes: 0 success, 1 a step failed (the pipeline stops there), 2 bad usage, 3 python not found.
A failing data quality check (step 3) stops the pipeline with exit code 1.
USAGE
}

FROM=0
while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --from) [ $# -ge 2 ] || { echo "--from needs a value" >&2; exit 2; }; FROM_ARG="$2"; shift 2 ;;
    --from=*) FROM_ARG="${1#--from=}"; shift ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [ -n "${FROM_ARG:-}" ]; then
  FROM=""
  for s in "${STEPS[@]}"; do
    IFS='|' read -r n name script kind <<<"$s"
    if [ "$FROM_ARG" = "$n" ] || [ "$FROM_ARG" = "$name" ]; then FROM="$n"; fi
  done
  if [ -z "$FROM" ]; then echo "unknown step: $FROM_ARG" >&2; usage >&2; exit 2; fi
fi

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else echo "python not found; set PYTHON" >&2; exit 3; fi
fi

cd "$ROOT"
mkdir -p logs
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$ROOT/logs/refresh_${STAMP}.log"

now_ms() { date +%s%3N; }
log() { printf '%s [refresh] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fmt_ms() { awk -v m="$1" 'BEGIN { printf "%.1f s", m / 1000 }'; }

main() {
  local t_start t0 t1 rc=0 s n name script kind
  local -a summary=()
  t_start="$(now_ms)"
  log "project root: $ROOT"
  log "python: $("$PY" -I -c 'import sys; print(sys.version.split()[0], sys.executable)')"
  log "log file: $LOG"
  log "options: from=$FROM SKIP_GEOCODE=${SKIP_GEOCODE:-0} SKIP_DOWNLOAD=${SKIP_DOWNLOAD:-0}"

  for s in "${STEPS[@]}"; do
    IFS='|' read -r n name script kind <<<"$s"
    if [ "$n" -lt "$FROM" ]; then
      log "step $n $name: not run (before --from)"
      summary+=("$n $name: not run")
      continue
    fi
    if [ "$n" = "0" ] && [ "${SKIP_DOWNLOAD:-0}" = "1" ]; then
      log "step 0 download: skipped (SKIP_DOWNLOAD=1)"
      summary+=("0 download: skipped")
      continue
    fi
    if [ ! -f "$script" ]; then
      if [ "$kind" = "optional" ]; then
        log "step $n $name: SKIPPED, $script does not exist (optional step)"
        summary+=("$n $name: skipped, script missing")
        continue
      fi
      log "step $n $name: FAILED, required script $script is missing"
      return 1
    fi
    if [ "$name" = "geocode" ] && [ "${SKIP_GEOCODE:-0}" = "1" ]; then
      if [ ! -f data/geocode_results.csv ]; then
        log "step 5 geocode: FAILED, SKIP_GEOCODE=1 but data/geocode_results.csv does not exist"
        return 1
      fi
      if ! grep -q SKIP_GEOCODE "$script"; then
        log "step 5 geocode: WARNING, $script does not read SKIP_GEOCODE, so it is not run (it would call the network)."
        log "step 5 geocode: data/geocode_results.csv is kept, but geocode_sample in the rebuilt database stays empty."
        summary+=("5 geocode: skipped (SKIP_GEOCODE=1, script has no reuse mode)")
        continue
      fi
    fi
    log "step $n $name: start ($PY -I $script)"
    t0="$(now_ms)"
    if "$PY" -I "$script" 2>&1 | sed -u 's/^/    | /'; then rc=0; else rc="${PIPESTATUS[0]}"; fi
    t1="$(now_ms)"
    if [ "$rc" -ne 0 ]; then
      log "step $n $name: FAILED with exit code $rc after $(fmt_ms $((t1 - t0)))"
      summary+=("$n $name: FAILED (exit $rc)")
      log "pipeline stopped at step $n"
      return 1
    fi
    log "step $n $name: ok in $(fmt_ms $((t1 - t0)))"
    summary+=("$n $name: ok, $(fmt_ms $((t1 - t0)))")
  done

  log "summary:"
  for s in "${summary[@]}"; do log "  $s"; done
  log "total duration: $(fmt_ms $(($(now_ms) - t_start)))"
  log "done"
}

if main 2>&1 | tee -a "$LOG"; then exit 0; else exit "${PIPESTATUS[0]}"; fi
