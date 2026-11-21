# Query timing

Measured by `src/08_benchmark.py` on this machine. All times are in milliseconds.

- Platform: Windows-11-10.0.26200-SP0, Python 3.13.7, DuckDB 2.0.1
- Database: `data/cuyahoga.duckdb`, 137,689 fact rows, 493 distinct tract identifiers across both tract geographies

**Limit of these numbers.** The database is small (about 138 thousand fact rows, 21.8 MB on disk). These timings show that this project is responsive; they say little about how the same design would behave on a large database, where indexing, partitioning, memory and concurrency would dominate and would have to be measured again.

## FastAPI endpoint, 50 sequential requests over one keep-alive connection

Requests cycle through all 30 indicator and vintage combinations of `/api/values` (average response 14.6 KB). Client-side wall time includes HTTP, JSON serialisation and the query; the server query time is reported by the endpoint itself (header `X-Query-Time-Ms`).

| Measure | min | median | p95 | max | mean |
|---|---|---|---|---|---|
| /api/values wall time (client) | 12.35 | 15.82 | 21.66 | 25.20 | 16.40 |
| /api/values query time (server) | 8.26 | 11.90 | 17.51 | 21.16 | 12.40 |
| /api/health wall time (50 requests) | 0.66 | 0.75 | 0.86 | 1.10 | 0.77 |

## Direct DuckDB queries, 20 runs each (read-only connection, run 1 is cold)

| Query | rows | run 1 | median | p95 | min | max |
|---|---|---|---|---|---|---|
| A. Indicator view, all tracts (v_indicator, one indicator and vintage) | 428 | 17.08 | 16.59 | 18.07 | 11.69 | 18.07 |
| B. Change on stable tracts (v_change_stable, one indicator) | 321 | 37.89 | 41.38 | 49.01 | 35.48 | 49.01 |
| C. Join to dim_tract (names and land area, ordered by value) | 428 | 25.06 | 15.56 | 25.06 | 13.90 | 25.06 |

The views compute every indicator from `fact_acs` at query time (no materialised table), so these numbers include the margin of error propagation and reliability classification.
