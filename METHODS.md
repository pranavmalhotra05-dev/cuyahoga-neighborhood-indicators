# Methods and decisions

**Sources.** ACS 5-year summary files from the Census Bureau (www2.census.gov/programs-surveys/acs/summary_file): the table-based files for 2020-2024 and the classic Ohio tract files for 2013-2017. TIGER/Line 2017 and 2024 tract boundaries, the 2010-2020 tract relationship file, and CPI-U annual averages from the BLS public API. Exact URLs, sizes, hashes and dates are in `data/source_manifest.csv`. The Census API was not used because it now answers every request with a missing key page.

**Tables.** B01002, B01003, B11003, B15003, B17001, B19013, B23025, B25002, B25003, B25004, B25044, B25070, B25077. All 157 cells of these tables are stored for every tract and for the county, each with its margin of error.

**Why two different file formats.** The 2020-2024 vintage is published as one file per table, the 2013-2017 vintage as sequence files whose column positions come from a lookup file. `src/01_ingest.py` reads both into one long table.

**Missing and suppressed values.** Negative nine-digit Census codes, blanks and the dot used in the older files never enter the database as numbers. They become NULL with a flag. A controlled estimate (county population) gets MOE 0. A median known only to sit at the top coded value is unavailable. An indicator is NULL if any of its cells is NULL.

**Margins of error.** Sum of cells: root sum of squares. Proportion: the Census formula, with the ratio formula as fallback. Difference between vintages: root sum of squares, assuming independent samples. CV = MOE / 1.645 / estimate; high below 0.15, medium to 0.30, low above.

**Tract boundaries changed in 2020.** 447 tracts in 2010 and 428 in 2020. A tract pair counts as stable when each covers at least 99 percent of the other by land area and no other tract overlaps either by more than 1 percent. Only stable tracts are compared. This leaves out the tracts that were split or merged, which are poorer on average (see the README), so the tract-level findings describe the stable part of the county.

**Money.** 2013-2017 dollars are moved to 2024 dollars with the CPI-U ratio.

**Geocoding.** See `outputs/geocode_report.md` and `data/geocode_source.md`.

**Known issues.**
- Two vintages only; the 2015-2019 and 2018-2022 vintages are not loaded.
- The change test is a screening rule at 90 percent confidence over several hundred tracts; some false signals are expected.
- Regression to the mean affects change by starting level; a rough simulation is in `src/09_analysis.py`.
- ACS tract estimates for rare conditions are noisy; most tract values of several indicators are in the low reliability class.
- The database is small (about 140 thousand fact rows). Query timings say nothing about large databases.
