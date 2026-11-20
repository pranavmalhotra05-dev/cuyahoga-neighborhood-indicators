-- Data quality checks. Every check inserts one row: id, description, expected, observed, status.
-- status is PASS, FAIL or INFO (INFO rows document facts that need a human reading, not a threshold).

CREATE OR REPLACE TABLE dq_results (
    check_id VARCHAR, description VARCHAR, expected VARCHAR, observed VARCHAR, status VARCHAR
);

-- 1. Row counts: every geography must have every one of the 157 ACS cells exactly once.
INSERT INTO dq_results
SELECT 'rows_' || vintage, 'fact rows for ' || vintage || ' tracts = tracts x ' || (SELECT count(*) FROM dim_variable) || ' cells',
       (n_tracts * (SELECT count(*) FROM dim_variable))::VARCHAR, n_rows::VARCHAR,
       CASE WHEN n_rows = n_tracts * (SELECT count(*) FROM dim_variable) THEN 'PASS' ELSE 'FAIL' END
FROM (SELECT vintage, count(DISTINCT geoid) AS n_tracts, count(*) AS n_rows
      FROM fact_acs WHERE geo_level = 'tract' GROUP BY vintage);

INSERT INTO dq_results
SELECT 'rows_county_' || vintage, 'county rows for ' || vintage || ' = one geography x all cells',
       (SELECT count(*) FROM dim_variable)::VARCHAR, count(*)::VARCHAR,
       CASE WHEN count(*) = (SELECT count(*) FROM dim_variable) AND count(DISTINCT geoid) = 1 THEN 'PASS' ELSE 'FAIL' END
FROM fact_acs WHERE geo_level = 'county' GROUP BY vintage;

-- 2. Tract count against the Census Bureau's own list of tracts (2010-2020 relationship file,
-- which lists every tract of both geographies) and against the TIGER/Line boundary file.
INSERT INTO dq_results
SELECT 'tract_count_2010', 'Cuyahoga tracts in ACS 2013-2017 = distinct 2010 tracts in the Census relationship file',
       (SELECT count(DISTINCT geoid_2010) FROM xwalk_tract_2010_2020)::VARCHAR,
       count(DISTINCT geoid)::VARCHAR,
       CASE WHEN count(DISTINCT geoid) = (SELECT count(DISTINCT geoid_2010) FROM xwalk_tract_2010_2020) THEN 'PASS' ELSE 'FAIL' END
FROM fact_acs WHERE geo_level = 'tract' AND vintage = '2013-2017';

INSERT INTO dq_results
SELECT 'tract_count_2020', 'Cuyahoga tracts in ACS 2020-2024 = distinct 2020 tracts in the Census relationship file',
       (SELECT count(DISTINCT geoid_2020) FROM xwalk_tract_2010_2020)::VARCHAR,
       count(DISTINCT geoid)::VARCHAR,
       CASE WHEN count(DISTINCT geoid) = (SELECT count(DISTINCT geoid_2020) FROM xwalk_tract_2010_2020) THEN 'PASS' ELSE 'FAIL' END
FROM fact_acs WHERE geo_level = 'tract' AND vintage = '2020-2024';

INSERT INTO dq_results
SELECT 'tiger_count_' || tract_vintage, 'TIGER/Line tracts (' || tract_vintage || ') = tracts with ACS data',
       (SELECT count(DISTINCT geoid) FROM fact_acs f JOIN dim_vintage v USING (vintage)
         WHERE f.geo_level = 'tract' AND v.tract_vintage = t.tract_vintage)::VARCHAR,
       count(*)::VARCHAR,
       CASE WHEN count(*) = (SELECT count(DISTINCT geoid) FROM fact_acs f JOIN dim_vintage v USING (vintage)
                              WHERE f.geo_level = 'tract' AND v.tract_vintage = t.tract_vintage) THEN 'PASS' ELSE 'FAIL' END
FROM dim_tract t GROUP BY tract_vintage;

-- 3. Join integrity.
INSERT INTO dq_results
SELECT 'orphan_fact_tracts', 'tract fact rows with no matching dim_tract row', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM fact_acs f JOIN dim_vintage v USING (vintage)
LEFT JOIN dim_tract t ON t.geoid = f.geoid AND t.tract_vintage = v.tract_vintage
WHERE f.geo_level = 'tract' AND t.geoid IS NULL;

INSERT INTO dq_results
SELECT 'tracts_without_facts', 'dim_tract rows with no ACS data in their vintage', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM dim_tract t JOIN dim_vintage v ON v.tract_vintage = t.tract_vintage
LEFT JOIN (SELECT DISTINCT vintage, geoid FROM fact_acs WHERE geo_level = 'tract') f
       ON f.vintage = v.vintage AND f.geoid = t.geoid
WHERE f.geoid IS NULL;

INSERT INTO dq_results
SELECT 'xwalk_tracts_known', 'crosswalk tracts missing from dim_tract (either geography)', '0',
       ((SELECT count(*) FROM xwalk_tract_2010_2020 x LEFT JOIN dim_tract t ON t.geoid = x.geoid_2010 AND t.tract_vintage = 2010 WHERE t.geoid IS NULL)
      + (SELECT count(*) FROM xwalk_tract_2010_2020 x LEFT JOIN dim_tract t ON t.geoid = x.geoid_2020 AND t.tract_vintage = 2020 WHERE t.geoid IS NULL))::VARCHAR,
       CASE WHEN ((SELECT count(*) FROM xwalk_tract_2010_2020 x LEFT JOIN dim_tract t ON t.geoid = x.geoid_2010 AND t.tract_vintage = 2010 WHERE t.geoid IS NULL)
      + (SELECT count(*) FROM xwalk_tract_2010_2020 x LEFT JOIN dim_tract t ON t.geoid = x.geoid_2020 AND t.tract_vintage = 2020 WHERE t.geoid IS NULL)) = 0 THEN 'PASS' ELSE 'FAIL' END;

INSERT INTO dq_results
SELECT 'geoid_format', 'tract GEOIDs that are not 11 digits starting with 39035', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM dim_tract WHERE NOT regexp_matches(geoid, '^39035[0-9]{6}$');

-- 4. Range checks on indicators.
INSERT INTO dq_results
SELECT 'range_rates', 'tract rate indicators outside 0-100 percent', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM v_indicator i JOIN indicator_def d USING (indicator_id)
WHERE d.kind = 'rate' AND i.value IS NOT NULL AND (i.value < 0 OR i.value > 100);

INSERT INTO dq_results
SELECT 'range_nonneg', 'tract counts, medians and MOEs below zero', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM v_indicator WHERE (value < 0) OR (moe < 0);

INSERT INTO dq_results
SELECT 'range_income', 'tract median household income outside 1,000-500,000 dollars', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM v_indicator WHERE indicator_id = 'median_hh_income' AND value IS NOT NULL AND (value < 1000 OR value > 500000);

INSERT INTO dq_results
SELECT 'subset_le_total', 'indicator cells where numerator exceeds denominator (impossible for a subset)', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM v_component n JOIN v_component d USING (vintage, geo_level, geoid, indicator_id)
JOIN indicator_def def USING (indicator_id)
WHERE n.role = 'num' AND d.role = 'den' AND def.kind = 'rate' AND n.est > d.est;

INSERT INTO dq_results
SELECT 'median_age_range', 'tract median age outside 10-90 years', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM v_indicator WHERE indicator_id = 'median_age' AND value IS NOT NULL AND (value < 10 OR value > 90);

-- 5. Margin of error sanity.
INSERT INTO dq_results
SELECT 'moe_present', 'cells with an estimate but no margin of error', '0', count(*)::VARCHAR,
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM fact_acs WHERE estimate IS NOT NULL AND moe IS NULL;

INSERT INTO dq_results
SELECT 'moe_wide', 'indicator values whose 90 percent MOE is larger than the value itself (CV over 0.61), tract rows',
       'informational', count(*)::VARCHAR || ' of ' || (SELECT count(*) FROM v_indicator WHERE geo_level = 'tract' AND cv IS NOT NULL), 'INFO'
FROM v_indicator WHERE geo_level = 'tract' AND cv > 1 / 1.645;

INSERT INTO dq_results
SELECT 'moe_rss_' || t.vintage, 'county MOE of poverty count B17001_002 vs root sum of squared tract MOEs, ' || t.vintage,
       'ratio between 0.7 and 1.3', round(c.moe / t.rss, 3)::VARCHAR,
       CASE WHEN c.moe / t.rss BETWEEN 0.7 AND 1.3 THEN 'PASS' ELSE 'FAIL' END
FROM (SELECT vintage, sqrt(sum(moe * moe)) AS rss FROM fact_acs WHERE geo_level = 'tract' AND variable = 'B17001_002' GROUP BY vintage) t
JOIN (SELECT vintage, moe FROM fact_acs WHERE geo_level = 'county' AND variable = 'B17001_002') c USING (vintage);

-- 6. Reconciliation to the county totals the Census Bureau publishes for the whole county.
-- Tract estimates of counts should add up to the county estimate. Small gaps come from
-- rounding and from tracts suppressed to NULL; the root sum of squared tract MOEs
-- approximates the county MOE.
INSERT INTO dq_results
WITH s AS (
  SELECT f.vintage, f.variable, sum(f.estimate) AS tract_sum, count(*) - count(f.estimate) AS n_null,
         sqrt(sum(f.moe * f.moe)) AS tract_moe_rss
  FROM fact_acs f WHERE f.geo_level = 'tract'
    AND f.variable IN ('B01003_001', 'B17001_001', 'B17001_002', 'B25002_001', 'B25002_003', 'B25003_003',
                       'B15003_001', 'B23025_005', 'B25044_001', 'B11003_001')
  GROUP BY f.vintage, f.variable),
 c AS (SELECT vintage, variable, estimate AS county_est, moe AS county_moe FROM fact_acs WHERE geo_level = 'county')
SELECT 'recon_' || s.vintage || '_' || s.variable,
       s.variable || ' tract sum vs county estimate, ' || s.vintage || ' (null tracts: ' || s.n_null || ')',
       'within 0.5 percent', round(100.0 * (s.tract_sum - c.county_est) / c.county_est, 3)::VARCHAR || ' percent (sum ' || s.tract_sum::BIGINT || ' vs ' || c.county_est::BIGINT || '; rss MOE ' || round(s.tract_moe_rss) || ' vs county MOE ' || round(c.county_moe) || ')',
       CASE WHEN abs((s.tract_sum - c.county_est) / c.county_est) <= 0.005 THEN 'PASS' ELSE 'FAIL' END
FROM s JOIN c USING (vintage, variable);

-- 7. Suppressed and missing values, reported explicitly.
INSERT INTO dq_results
SELECT 'flags_' || vintage, 'cells with a Census sentinel or blank value in ' || vintage || ' (tract level)',
       'informational',
       count(*) FILTER (WHERE estimate IS NULL)::VARCHAR || ' null estimates of ' || count(*) || ' cells; tracts with any: '
         || count(DISTINCT geoid) FILTER (WHERE estimate IS NULL), 'INFO'
FROM fact_acs WHERE geo_level = 'tract' GROUP BY vintage;

INSERT INTO dq_results
SELECT 'unavailable_indicator_' || vintage, 'tract indicator values that are NULL (unavailable) in ' || vintage,
       'informational', count(*)::VARCHAR || ' of ' || (SELECT count(*) FROM v_indicator i2 WHERE i2.vintage = v.vintage AND i2.geo_level = 'tract'), 'INFO'
FROM v_indicator v WHERE geo_level = 'tract' AND value IS NULL GROUP BY vintage;

-- 8. Crosswalk: overlaps of each tract must add up to its land area (within 0.5 percent).
INSERT INTO dq_results
SELECT 'xwalk_area_2020', '2020 tracts whose land overlaps in the relationship file do not add up to their land area (0.5 percent)',
       '0', count(*)::VARCHAR, CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM (SELECT geoid_2020, max(aland_2020) AS a, sum(aland_overlap) AS o FROM xwalk_tract_2010_2020 GROUP BY 1)
WHERE a > 0 AND abs(o - a) > 0.005 * a;

INSERT INTO dq_results
SELECT 'stable_tracts', 'tracts with essentially unchanged boundaries between 2010 and 2020 (used for change analysis)',
       'informational', (SELECT count(*) FROM v_stable_tract)::VARCHAR || ' of ' || (SELECT count(*) FROM dim_tract WHERE tract_vintage = 2020) || ' (2020) and ' || (SELECT count(*) FROM dim_tract WHERE tract_vintage = 2010) || ' (2010)', 'INFO';
