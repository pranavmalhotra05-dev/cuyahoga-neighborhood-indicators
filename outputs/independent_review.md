# Independent review of the headline numbers

Method: every number below was recomputed by `tests/independent_recompute.py` from the raw files only (ACS 2020-2024 `.dat` files, the 2013-2017 classic summary file read by sequence file and start position, the tab20 crosswalk, and the BLS API). The DuckDB file, `sql/`, and `src/` were not used and were read only after the computation was written. Run with `python -I tests/independent_recompute.py` (add `--offline` to skip the BLS call). The script exits non-zero while any claim differs, and currently reports 123 MATCH and 4 MISMATCH.

Tolerance: exact for counts, 0.01 for rates, and the rounding of the project's own figure when it is coarser (for example one decimal).

## Claims

| Claim | Project | Recomputed | Verdict |
|---|---|---|---|
| Tracts 2013-2017 (rows in file) | 447 | 447 | MATCH |
| Tracts 2020-2024 (rows in file) | 428 | 428 | MATCH |
| County poverty 2013-2017 | 18.30 | 18.30 | MATCH |
| County poverty 2013-2017 MOE | 0.38 | 0.383 | MATCH |
| County poverty 2020-2024 | 16.07 | 16.074 | MATCH |
| County poverty 2020-2024 MOE | 0.44 | 0.437 | MATCH |
| County poverty change | -2.23 | -2.226 | MATCH |
| County poverty change MOE | 0.58 | 0.581 | MATCH |
| County median income 2013-2017 in 2024 dollars | 59,789 | 59,789.29 | MATCH |
| County median income 2020-2024 | 64,468 | 64,468 | MATCH |
| Income change (2024 dollars) | 4,679 | 4,678.71 | MATCH |
| Income change MOE | 892 | 891.98 | MATCH |
| CPI-U 2017 and 2024 in csv vs BLS API | 245.120, 313.689 | 245.120, 313.689 | MATCH (all eight years 2017 to 2024 match) |
| Stable tracts | 324 | 324 | MATCH (see issue 3 on the definition) |
| Stable tracts with poverty in both vintages | 321 | 321 | MATCH |
| Median / mean poverty change | -1.07 / -1.93 | -1.07 / -1.93 | MATCH |
| Changes beyond the 90% MOE of the difference | 50 (15.6%) | 50 (15.58%) | MATCH |
| Distinguishable down / up | 44 / 6 | 44 / 6 | MATCH |
| Any down / any up | 184 / 137 | 184 / 137 | MATCH |
| Median MOE of the difference | 10.05 | 10.05 | MATCH |
| Largest distinguishable drop / rise | -30.9 / 30.7 | -30.91 / 30.67 | MATCH |
| Spearman rank correlation | 0.828 | 0.828 | MATCH |
| Quartile medians of change (lowest to highest) | 0.95, -1.92, -3.47, -7.60 | same | MATCH |
| Quartile medians of start rate | 3.6, 10.0, 20.8, 39.8 | 3.58, 10.03, 20.85, 39.77 | MATCH |
| Quartile shares distinguishable | 4.9, 15.0, 21.2, 21.2 | 4.94, 15.00, 21.25, 21.25 | MATCH |
| Stable tracts with poverty 30% or more (2013-2017, 2020-2024, both) | 76, 58, 47 | 76, 58, 47 | MATCH |
| 2020-2024 tracts with a poverty value | 421 | 421 | MATCH |
| Share of tracts with CV above 0.30 | 57.0 | 57.01 | MATCH |
| Median / 90th percentile tract MOE (points) | 7.0 / 17.1 | 7.01 / 17.15 | MATCH |
| Poverty 90th percentile cutoff | 44.0 | 43.96 | MATCH |
| Top 20 tracts whose interval reaches below the cutoff | 10 | 10 | MATCH |
| Median poverty, stable vs changed tracts | 12.4 / 19.4 | 12.42 / 19.45 | MATCH |
| Tracts "over p90" | 43 | 42 strictly above, 43 at or above | MISMATCH on wording (issue 2) |
| Tracts "over p90" whose interval reaches below | 32 | 31 strictly above, 32 at or above | MISMATCH on wording (issue 2) |
| Changed boundary tracts 2020 | 100 | 104 of 428; 100 only among tracts with a poverty value | MISMATCH on label (issue 1) |
| Tract sum vs county B17001_001 and _002, 2020-2024 | n/a | 1,221,489 and 196,342, equal to county | MATCH |
| Tract sum vs county B17001_001 and _002, 2013-2017 | n/a | 1,230,956 and 225,265, equal to county | MATCH |
| County rent burden 30%+ change | -2.05 | -2.045 | MATCH |
| County rent burden 30%+ change MOE | 1.11 | 1.353 with published MOEs of B25070_001 and _011; 1.114 with the project's sum of cells 2 to 10 | MISMATCH by method (issue 4) |
| County other vacant change | -1.69 | -1.689 | MATCH |
| Rent burden 30%+ rates | 50.40 (2013-2017), 48.36 (2020-2024) | 50.401, 48.356 | MATCH |
| All 15 county indicators, both vintages, change and change MOE (in `outputs/analysis_county_change.csv`) | see file | same | MATCH (value, change, and MOE) |

Not independently reproduced: the four "artifact if no true change" figures, which come from a seeded simulation (see issue 6).

## Hand verification and sentinels

Five tracts drawn at random (seed fixed in the script) were parsed from the raw `.dat` bytes with a plain string split, and one 2013-2017 tract was parsed from the raw sequence and margin files through the geography file. All six agree with the vectorized code to 1e-9. Example: tract 39035151800 has 504 of 1,348 below poverty, so 37.39 percent with a 12.10 point MOE.

Sentinels: no negative number survives in any recomputed frame (asserted). The B17001, B25070 and county rows contain no sentinel codes. B19013 has 13 county tracts with a missing median (code -666666666 or -222222222) and 2 tracts whose MOE code is -333333333 (top-coded median); the project nulls all of them, which is the right treatment. Seven 2020-2024 tracts have zero population and so no poverty rate, which is why 428 tracts give 421 values. In the 2013-2017 files, B17001 has no blank or dot cells for the 447 tracts, and no negative or non-numeric tokens were found in any table read.

## Issues found in the pipeline logic, ranked

1. Mislabeled count, `changed_boundary_tracts_2020 = 100` (`src/09_analysis.py`, section 4). The count is made after the join to `v_indicator` with `value IS NOT NULL`, so it covers only changed tracts that have a poverty rate (421 minus 321). By geography 428 minus 324 equals 104 tracts changed. Any text that says "100 tracts changed boundaries" is off by four. Fix the label, or report both numbers.
2. "Over the 90th percentile" is computed with `>=` (`poverty_tracts_over_p90`, `poverty_tracts_over_p90_interval_reaches_below`). The tract that sits exactly on the cutoff is included and always counts as "reaching below" the cutoff, so 43 and 32 should read 42 and 31, or the wording should be "at or above". The cutoff is also rounded to 44.0 while the true value is 43.96, which can mislead a reader checking tracts near 44.
3. The "one to one" clause in `v_stable_tract` is vacuous. If both overlap shares are at least 0.99, any other crosswalk row for either tract has a share of at most 0.01, so the `sig` filter (both shares above 0.01) can never add a second row. The result equals the plain 99 percent mutual-overlap rule (324). Read literally ("no other row at all"), only 228 tracts are one-to-one; 96 of the 324 have a sliver row. Both readings should be stated. With the strict reading the poverty results shift modestly (226 tracts, median change -1.15, mean -1.71, 27 down and 5 up distinguishable), so the findings are not sensitive to it. A related limit: stability is defined by land area, not population, and 1 percent of the land of a dense tract can hold more than 1 percent of its people.
4. Rent burden MOE uses a denominator built as the root sum of squares of cells 2 to 10 (`sql/02_indicator_defs.sql`). The estimate is correct (it excludes "not computed", which is the sound choice; including B25070_001 would give -1.55 instead of -2.05). The MOE then comes out at 1.11 for the change, against 1.35 if the published MOEs of B25070_001 and B25070_011 are used. Summing nine cell MOEs ignores covariance and the published total's design-based MOE. This is within the Census approximation guidance, but the claim that the change is distinguishable holds either way (2.05 against 1.11 or 1.35).
5. The statement in `docs/technical_standards.md` section 3 that "with 321 comparisons a few false signals are expected" is understated. At 90 percent confidence a no-change world flags about 32 of 321 tracts (about 16 per direction). Observed is 50 (44 down, 6 up). So roughly two thirds of the flagged tracts could be noise if there were no change at all, and only the excess of downward moves (44 against about 16) is clearly beyond chance. The analysis text should say this plainly. The independence of tract tests and the regression-to-the-mean effect are further reasons the flag count is only a screening figure.
6. The regression-to-the-mean simulation in `src/09_analysis.py` treats the noisy 2013-2017 estimates as the truth, splits the difference variance equally between vintages, and does not clip simulated rates at zero or 100. It is labeled a heuristic in the code, which is honest, but the four artifact figures in the numbers file should be described the same way wherever they are quoted. It is not independently reproducible without the same random stream.
7. `cv` is NULL when the estimate is 0, and `(v.cv > 0.30).mean()` then counts a zero-poverty tract as not low reliability. No 2020-2024 tract has a zero poverty rate, so the 57.0 percent is unaffected today, but the code would silently understate low-reliability shares on another indicator or vintage (the `reliability` view column does handle zero as its own class).
8. Untested edge cases: the test folder was empty. Not covered by any check: a tract with an estimate but a sentinel MOE (it correctly goes NULL via `n_ok`, but nothing asserts it), zero-population tracts, the controlled-estimate MOE rule (-555555555 becomes MOE 0, which the project applies to counts such as county population), and stable pairs with no usable rate (three exist: 39035980100, 39035980500, 39035981100). The recompute script exercises the sentinel and zero-population cases for the tables it reads, but it is not a regression suite for the pipeline.
9. Caveat, not a bug: the 2020-2024 file includes survey year 2020, whose collection was disrupted. The analysis does not mention it, and it could slightly affect the comparison with 2013-2017.

Not found: errors in the poverty, income, rent burden, and other indicator definitions (cell mappings were checked against the table shells and all 15 county indicators reproduce), in the sentinel handling, in the CPI values, in the proportion MOE implementation, or in the 2013-2017 sequence file parsing. The core county and tract poverty findings reproduce exactly.

## Follow-up by the project owner

- Issue 1: the key was renamed to `not_stable_2020_tracts_with_poverty_value` (100) and `not_stable_2020_tracts_all` (104) in `src/09_analysis.py`; the README uses 104 and 100 with the right labels. The test script now reads the new keys.
- Issue 2: the "p90" counts in `outputs/analysis_numbers.json` are at-or-above the cutoff (43 and 32); the README does not quote them. The remaining MISMATCH lines are the wording difference only.
- Issue 3: the README and technical standards now describe the 1 percent sliver rule and that stability is judged by land area. The strict one-to-one reading (228 tracts) is mentioned as a limit.
- Issue 4: documented in the README limits (1.11 versus 1.35; the change is distinguishable either way).
- Issue 5 and 9: wording and the 2020 survey-year caveat added to the README and technical standards.
- Issues 6 to 8 are open: the simulation was not independently reproduced, a zero estimate gets a NULL CV, and edge-case tests for zero-population tracts are not written.
