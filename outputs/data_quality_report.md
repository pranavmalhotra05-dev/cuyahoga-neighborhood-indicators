# Data quality report

Checks: 47. PASS 41, FAIL 0, INFO 6.

| Status | Check | Expected | Observed |
|---|---|---|---|
| PASS | tract GEOIDs that are not 11 digits starting with 39035 | 0 | 0 |
| PASS | tract median age outside 10-90 years | 0 | 0 |
| PASS | cells with an estimate but no margin of error | 0 | 0 |
| PASS | county MOE of poverty count B17001_002 vs root sum of squared tract MOEs, 2013-2017 | ratio between 0.7 and 1.3 | 0.994 |
| PASS | county MOE of poverty count B17001_002 vs root sum of squared tract MOEs, 2020-2024 | ratio between 0.7 and 1.3 | 0.858 |
| PASS | tract fact rows with no matching dim_tract row | 0 | 0 |
| PASS | tract median household income outside 1,000-500,000 dollars | 0 | 0 |
| PASS | tract counts, medians and MOEs below zero | 0 | 0 |
| PASS | tract rate indicators outside 0-100 percent | 0 | 0 |
| PASS | B01003_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 1257401 vs 1257401; rss MOE 5820.0 vs county MOE 0.0) |
| PASS | B11003_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 304670 vs 304670; rss MOE 2034.0 vs county MOE 2121.0) |
| PASS | B15003_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 874449 vs 874449; rss MOE 3828.0 vs county MOE 44.0) |
| PASS | B17001_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 1230956 vs 1230956; rss MOE 5713.0 vs county MOE 955.0) |
| PASS | B17001_002 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 225265 vs 225265; rss MOE 4749.0 vs county MOE 4719.0) |
| PASS | B23025_005 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 57668 vs 57668; rss MOE 1689.0 vs county MOE 1536.0) |
| PASS | B25002_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 619305 vs 619305; rss MOE 1338.0 vs county MOE 547.0) |
| PASS | B25002_003 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 81684 vs 81684; rss MOE 1762.0 vs county MOE 2136.0) |
| PASS | B25003_003 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 221249 vs 221249; rss MOE 2154.0 vs county MOE 2284.0) |
| PASS | B25044_001 tract sum vs county estimate, 2013-2017 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 537621 vs 537621; rss MOE 1961.0 vs county MOE 2085.0) |
| PASS | B01003_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 1245873 vs 1245873; rss MOE 10126.0 vs county MOE 0.0) |
| PASS | B11003_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 296308 vs 296308; rss MOE 3302.0 vs county MOE 2553.0) |
| PASS | B15003_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 888313 vs 888313; rss MOE 6650.0 vs county MOE 53.0) |
| PASS | B17001_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 1221489 vs 1221489; rss MOE 10088.0 vs county MOE 637.0) |
| PASS | B17001_002 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 196342 vs 196342; rss MOE 6215.0 vs county MOE 5333.0) |
| PASS | B23025_005 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 43117 vs 43117; rss MOE 2180.0 vs county MOE 2024.0) |
| PASS | B25002_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 615331 vs 615331; rss MOE 3878.0 vs county MOE 252.0) |
| PASS | B25002_003 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 60780 vs 60780; rss MOE 1950.0 vs county MOE 1966.0) |
| PASS | B25003_003 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 225378 vs 225378; rss MOE 3518.0 vs county MOE 2877.0) |
| PASS | B25044_001 tract sum vs county estimate, 2020-2024 (null tracts: 0) | within 0.5 percent | 0.0 percent (sum 554551 vs 554551; rss MOE 4000.0 vs county MOE 1919.0) |
| PASS | fact rows for 2013-2017 tracts = tracts x 157 cells | 70179 | 70179 |
| PASS | fact rows for 2020-2024 tracts = tracts x 157 cells | 67196 | 67196 |
| PASS | county rows for 2013-2017 = one geography x all cells | 157 | 157 |
| PASS | county rows for 2020-2024 = one geography x all cells | 157 | 157 |
| PASS | indicator cells where numerator exceeds denominator (impossible for a subset) | 0 | 0 |
| PASS | TIGER/Line tracts (2010) = tracts with ACS data | 447 | 447 |
| PASS | TIGER/Line tracts (2020) = tracts with ACS data | 428 | 428 |
| PASS | Cuyahoga tracts in ACS 2013-2017 = distinct 2010 tracts in the Census relationship file | 447 | 447 |
| PASS | Cuyahoga tracts in ACS 2020-2024 = distinct 2020 tracts in the Census relationship file | 428 | 428 |
| PASS | dim_tract rows with no ACS data in their vintage | 0 | 0 |
| PASS | 2020 tracts whose land overlaps in the relationship file do not add up to their land area (0.5 percent) | 0 | 0 |
| PASS | crosswalk tracts missing from dim_tract (either geography) | 0 | 0 |
| INFO | cells with a Census sentinel or blank value in 2013-2017 (tract level) | informational | 32 null estimates of 70179 cells; tracts with any: 16 |
| INFO | cells with a Census sentinel or blank value in 2020-2024 (tract level) | informational | 54 null estimates of 67196 cells; tracts with any: 26 |
| INFO | indicator values whose 90 percent MOE is larger than the value itself (CV over 0.61), tract rows | informational | 1147 of 12717 |
| INFO | tracts with essentially unchanged boundaries between 2010 and 2020 (used for change analysis) | informational | 324 of 428 (2020) and 447 (2010) |
| INFO | tract indicator values that are NULL (unavailable) in 2013-2017 | informational | 69 of 6705 |
| INFO | tract indicator values that are NULL (unavailable) in 2020-2024 | informational | 124 of 6420 |
