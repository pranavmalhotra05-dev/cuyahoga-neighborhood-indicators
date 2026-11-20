# Technical standards

These are the rules the project follows so that a number in the viewer can be traced back to a published table and so that two people running the pipeline get the same result. They are written the way a small community data center would write them for its own database.

## 1. Sources

- Only public sources: ACS 5-year summary files and TIGER/Line boundaries from the U.S. Census Bureau, the 2010-2020 tract relationship file, and CPI-U from the Bureau of Labor Statistics.
- Every raw file is listed in `data/source_manifest.csv` with its URL, size, SHA-256 and download date. Raw files are not committed; `src/00_download.py` fetches them again.
- Vintages are named by the ACS period, for example `2020-2024`. A vintage is tied to one tract geography (2010 or 2020) in `dim_vintage`.
- The Census API now requires a key for every request, so the bulk summary files are used instead. They are the same published tables.

## 2. Geography and identifiers

- A tract is identified by its 11 character GEOID (state 2, county 3, tract 6). The pair (tract geography year, GEOID) is the key, because a GEOID can mean different land in 2010 and 2020.
- Only tracts with essentially unchanged boundaries are compared tract by tract across vintages: land overlap of at least 99 percent of both tracts, one to one (`v_stable_tract`). The result is cross-checked with a GeoPandas overlay in `src/04_spatial_checks.py`.
- Point data (geocoded addresses) is assigned to tracts with a spatial join in an explicit coordinate reference system, and the Census geocoder's own tract assignment is compared against it.

## 3. Estimates, margins of error and suppression

- Every ACS cell is stored with its estimate and its 90 percent margin of error (MOE). Nothing is stored without its MOE, and `dq_results` fails if an estimate has no MOE.
- Census sentinel codes are never kept as numbers. They become NULL with a `flag` that records what they meant: no estimate, too few sample cases, a median in an open-ended interval, or (2013-2017 files) a dot for suppressed. A margin of error code of controlled estimate (county population totals) becomes MOE 0 with a flag. A median that is only known to be at the top coded value is treated as unavailable.
- An indicator is NULL if any cell of its numerator or denominator is NULL. No imputation is done.
- MOE of a sum is the square root of the sum of squared MOEs. MOE of a proportion uses the Census formula for a proportion, falling back to the ratio formula when the radicand is negative. MOE of a difference between two vintages is the square root of the sum of squared MOEs, which assumes the two five-year samples are independent (they do not overlap in time, so this is reasonable).
- Coefficient of variation CV = (MOE / 1.645) / estimate. Reliability classes: high when CV is below 0.15, medium from 0.15 to 0.30, low above 0.30. These thresholds are a common convention, not a Census rule. Maps and the viewer show the class next to every value.
- A change is called distinguishable when its absolute value is larger than the MOE of the difference. It is a screening rule at 90 percent confidence, and with 321 comparisons a few false signals are expected.

## 4. Money

- Dollar values keep the price year of their vintage. Comparisons convert 2013-2017 dollars to 2024 dollars with the ratio of CPI-U annual averages (`data/cpi_u_annual.csv`). The ACS already adjusts to the end year of its period, so this is a second-order approximation for the five years in between.

## 5. Database

- DuckDB, one file, built from scratch by `src/02_build_db.py` with `CREATE OR REPLACE`, so a rebuild is idempotent.
- Fact table is long (vintage, geo level, geoid, variable). Indicators are views over it, defined by data in `indicator_def` and `indicator_cell`, not by hard-coded SQL per indicator.
- Primary keys and foreign keys are declared. Checks in `sql/04_checks.sql` cover row counts, joins, ranges, MOE sanity, tract counts against the Census relationship file and TIGER, and reconciliation of tract sums to published county totals.
- The pipeline stops when a check fails.

## 6. Reproducibility and operations

- Scripts are numbered and run with `python -I` so no local module can shadow a standard one.
- `scripts/refresh.sh` runs everything end to end, logs each step with its duration, and exits non-zero on failure. `scripts/backup.sh` writes a verified, hashed, rotated archive of the database. See [shell_automation.md](shell_automation.md).
- Seeds are fixed wherever randomness is used (address sample, simulation).

## 7. Data security and privacy

- The project uses only published aggregate data and the public addresses of institutions (schools or libraries). No person-level or household-level data is stored or processed.
- Small-area estimates are not suppressed beyond what the Census Bureau already applies, but tracts with low reliability are labelled, and the text warns against ranking tracts on their point estimates.
- Backups are checksummed and verified after writing. A restore never overwrites the live database unless asked.
- No credentials or API keys are needed or stored in the repository.

## 8. Documentation

- Indicator definitions and the data dictionary are generated from the database (`src/10_docs.py`) so they cannot drift from the code.
- Every number in the README and the analysis write-up comes from a script output that is committed under `outputs/`.
