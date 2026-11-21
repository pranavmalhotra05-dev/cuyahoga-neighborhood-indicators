# Shell automation

Three bash scripts in `scripts/` run the pipeline, back up the database and start the web server. All of them resolve the project root from their own location, so they can be started from any directory. They use `python3` if it works, otherwise `python`, or the interpreter named in the `PYTHON` environment variable. Pipeline steps are run as `python -I script.py`.

## Running on Windows (Git Bash)

Open Git Bash (it ships with Git for Windows) and run, from any folder:

```bash
bash "/c/Users/<you>/Job research/projects/cuyahoga_neighborhood_indicators/scripts/refresh.sh"
```

Quote the path when it contains spaces. In Git Bash the Windows drive `C:` is `/c`. Alternatively `cd` into the project and run `bash scripts/refresh.sh`. Do not run the scripts with PowerShell or cmd directly; call `bash` explicitly. The scripts need `tar`, `sha256sum`, `awk`, `sed` and `date` with `%N` support, all of which Git Bash provides. If `tar` is missing the backup falls back to a `.zip` written with Python.

## Running on Linux

```bash
cd /path/to/cuyahoga_neighborhood_indicators
bash scripts/refresh.sh          # or: chmod +x scripts/*.sh && ./scripts/refresh.sh
```

The scripts are stored with LF line endings (see `.gitattributes`). On macOS the BSD `date` does not support `%N`, so install GNU coreutils (`gdate`) or run on Linux.

## scripts/refresh.sh

Runs the whole pipeline in order and stops at the first failing step.

| Step | Name | Script | Kind | What it does |
|---|---|---|---|---|
| 0 | download | `src/00_download.py` | required | Downloads Census and BLS inputs; files already present are kept, and `data/source_manifest.csv` is refreshed. |
| 1 | ingest | `src/01_ingest.py` | required | Extracts the ACS cells for Cuyahoga County into `data/interim/acs_long.parquet`. |
| 2 | build | `src/02_build_db.py` | required | Rebuilds `data/cuyahoga.duckdb` from the SQL in `sql/01..03`. |
| 3 | checks | `src/03_checks.py` | required | Runs the data quality checks and writes `outputs/data_quality_report.md`; exits 1 if any check FAILs, which stops the pipeline. |
| 4 | spatial | `src/04_spatial_checks.py` | optional | Spatial checks of the tract layers. |
| 5 | geocode | `src/05_geocode.py` | optional | Geocodes the public address sample (network). |
| 6 | maps | `src/06_maps.py` | optional | Writes the static map images to `docs/img/`. |
| 7 | web | `src/07_export_web.py` | required | Writes `web/data/*.geojson` and `web/data/indicators.json` for the viewer. |
| 9 | analysis | `src/09_analysis.py` | optional | Analysis numbers for the write-up. |

Optional steps whose script does not exist are skipped with a clear log line; a missing required script is an error.

Usage:

```bash
bash scripts/refresh.sh --help
bash scripts/refresh.sh                    # everything
bash scripts/refresh.sh --from checks      # start at a step, by name or number
SKIP_GEOCODE=1 bash scripts/refresh.sh     # do not call the network geocoder
SKIP_DOWNLOAD=1 bash scripts/refresh.sh    # skip step 0
```

Every line is timestamped, each step reports its duration, and the same output is written to `logs/refresh_YYYYMMDD_HHMMSS.log` (the `logs/` folder is ignored by git).

Exit codes: 0 success; 1 a step failed (the pipeline stops there); 2 bad usage; 3 Python not found.

`SKIP_GEOCODE=1`: step 5 would call the Census geocoder. With this variable set, the script runs `src/05_geocode.py` only if that file reads `SKIP_GEOCODE` (so it can reload `data/geocode_results.csv` without the network). The current `05_geocode.py` has no such mode, so the script logs a warning and skips it. Step 2 rebuilds the database, which empties the `geocode_sample` table, so a run with `SKIP_GEOCODE=1` leaves that table empty and the geocoded-points map is drawn without points until `05_geocode.py` gains a reload mode.

### Measured run

`SKIP_GEOCODE=1 bash scripts/refresh.sh`, started from a different directory, on Windows 11 with Git Bash, all downloads already present (exit code 0):

| Step | Duration |
|---|---|
| 0 download | 1.2 s |
| 1 ingest | 7.6 s |
| 2 build | 2.2 s |
| 3 checks | 1.1 s |
| 4 spatial | 2.3 s |
| 5 geocode | skipped (see above) |
| 6 maps | 4.4 s |
| 7 web | 1.4 s |
| 9 analysis | 2.3 s |
| total | 24.1 s |

A simulated failure of step 3 (a wrapper returning exit code 7) stopped the pipeline at that step with a final exit code of 1, and `--from nonsense` returned exit code 2.

## scripts/backup.sh

```bash
bash scripts/backup.sh                                # create a backup
bash scripts/backup.sh --restore backups/cuyahoga_YYYYMMDD_HHMMSS.tar.gz
bash scripts/backup.sh --restore ARCHIVE --force      # also replace the live files
KEEP=14 bash scripts/backup.sh                        # keep the newest 14 instead of 7
```

Creating a backup:

1. Runs `CHECKPOINT` on `data/cuyahoga.duckdb` through Python so no `.wal` file is left. If the database is open elsewhere and a WAL file exists, it stops with exit code 1.
2. Copies the database, `data/source_manifest.csv` and `sql/*.sql` to a staging folder and writes `SHA256SUMS.txt` (SHA-256 of each file) next to them.
3. Creates `backups/cuyahoga_YYYYMMDD_HHMMSS.tar.gz` (or `.zip` when `tar` is missing).
4. Verifies the archive: lists it, extracts it into a temporary folder and re-hashes every file against the manifest.
5. Keeps only the newest 7 backups (`KEEP`), then prints the archive path, size, duration and count.

Restoring: the archive is extracted into `backups/restore_scratch_<timestamp>/`, the hashes are verified and the restored database is opened read-only to count `fact_acs` rows. The live database is not touched unless `--force` is given; with `--force` the live database is first copied to `data/cuyahoga.duckdb.before_restore`, then the database, manifest and SQL files are replaced and the scratch folder is removed. A tampered archive fails the hash check and the script exits with code 1.

Exit codes: 0 success; 1 failure (checkpoint, verification, hash mismatch, missing file); 2 bad usage; 3 Python or a hash tool not found.

Measured on the same machine: the first backup took 1.71 s and produced an archive of 1557455 bytes (the database file is 21.8 MB, see `outputs/query_timing.md`); with `KEEP=2` a third backup removed the oldest one; a restore to the scratch folder took 0.58 s and left the live database hash unchanged; a restore with `--force` took 0.78 s and the restored database hash equalled the live one; an archive with one appended byte in the database failed the hash check with exit code 1.

## scripts/run_server.sh

```bash
bash scripts/run_server.sh                 # http://127.0.0.1:8000/
PORT=8080 HOST=0.0.0.0 bash scripts/run_server.sh
```

Starts the FastAPI app in `src/app.py`, which serves `web/` and the endpoints `/api/health`, `/api/indicators` and `/api/values?indicator=&vintage=`. The root URL redirects to `/index.html?api=1`; with `?api=1` the viewer offers a checkbox to read values from the live database instead of the static JSON. The viewer works without the server (static host, for example GitHub Pages at a sub-path) because every URL in it is relative.

To view only the static viewer without the API: `cd web && python -m http.server 8000`.

Latency measurements for the endpoint and for three direct DuckDB queries are in `outputs/query_timing.md`, produced by `python -I src/08_benchmark.py`.
