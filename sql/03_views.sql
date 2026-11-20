-- Indicator views. MOE propagation follows the Census Bureau ACS handbook:
--   sum of cells:  MOE = sqrt(sum of squared MOEs)
--   proportion p = N/D with N a subset of D:  MOE = sqrt(MOE_N^2 - p^2 * MOE_D^2) / D
--   if the radicand is negative use the ratio formula  sqrt(MOE_N^2 + p^2 * MOE_D^2) / D
-- Standard error = MOE / 1.645 (ACS MOEs are at the 90 percent level); CV = SE / estimate.
-- Any numerator or denominator cell with a missing estimate makes the whole indicator NULL.

CREATE OR REPLACE VIEW v_component AS
SELECT f.vintage, f.geo_level, f.geoid, c.indicator_id, c.role,
       sum(f.estimate)          AS est,
       sqrt(sum(f.moe * f.moe)) AS moe,
       count(*)                 AS n_cells,
       count(f.estimate)        AS n_cells_with_estimate,
       count(f.moe)             AS n_cells_with_moe
FROM fact_acs f
JOIN indicator_cell c USING (variable)
GROUP BY f.vintage, f.geo_level, f.geoid, c.indicator_id, c.role;

CREATE OR REPLACE VIEW v_indicator AS
WITH n AS (SELECT * FROM v_component WHERE role = 'num'),
     d AS (SELECT * FROM v_component WHERE role = 'den'),
     j AS (
       SELECT n.vintage, n.geo_level, n.geoid, n.indicator_id, def.kind,
              n.est AS n_est, n.moe AS n_moe, d.est AS d_est, d.moe AS d_moe,
              (n.n_cells_with_estimate = n.n_cells AND n.n_cells_with_moe = n.n_cells) AS n_ok,
              (d.indicator_id IS NULL OR (d.n_cells_with_estimate = d.n_cells AND d.n_cells_with_moe = d.n_cells)) AS d_ok
       FROM n
       JOIN indicator_def def USING (indicator_id)
       LEFT JOIN d USING (vintage, geo_level, geoid, indicator_id)
     ),
     c AS (
       SELECT j.*,
              CASE WHEN kind = 'rate' THEN
                     CASE WHEN d_est > 0 AND n_ok AND d_ok THEN 100.0 * n_est / d_est END
                   ELSE CASE WHEN n_ok THEN n_est END END AS value,
              CASE WHEN kind = 'rate' THEN
                     CASE WHEN d_est > 0 AND n_ok AND d_ok THEN
                       100.0 * CASE
                         WHEN n_moe^2 - (n_est / d_est)^2 * d_moe^2 >= 0
                           THEN sqrt(n_moe^2 - (n_est / d_est)^2 * d_moe^2) / d_est
                         ELSE sqrt(n_moe^2 + (n_est / d_est)^2 * d_moe^2) / d_est END
                     END
                   ELSE CASE WHEN n_ok THEN n_moe END END AS moe
       FROM j
     )
SELECT c.vintage, c.geo_level, c.geoid, c.indicator_id, c.value, c.moe,
       c.d_est AS denominator,
       CASE WHEN c.value IS NOT NULL AND c.moe IS NOT NULL AND c.value <> 0
            THEN (c.moe / 1.645) / abs(c.value) END AS cv,
       CASE WHEN c.value IS NULL THEN 'unavailable'
            WHEN c.moe IS NULL THEN 'no_moe'
            WHEN c.value = 0 THEN 'zero_estimate'
            WHEN (c.moe / 1.645) / abs(c.value) < 0.15 THEN 'high'
            WHEN (c.moe / 1.645) / abs(c.value) <= 0.30 THEN 'medium'
            ELSE 'low' END AS reliability
FROM c;

-- Dollar indicators expressed in 2024 dollars (CPI-U ratio); other indicators unchanged.
CREATE OR REPLACE VIEW v_indicator_adj AS
SELECT i.*,
       CASE WHEN def.kind = 'median_dollars'
            THEN i.value * (SELECT cpi_u FROM dim_vintage WHERE vintage = '2020-2024') / v.cpi_u
            ELSE i.value END AS value_2024usd,
       CASE WHEN def.kind = 'median_dollars'
            THEN i.moe * (SELECT cpi_u FROM dim_vintage WHERE vintage = '2020-2024') / v.cpi_u
            ELSE i.moe END AS moe_2024usd
FROM v_indicator i
JOIN indicator_def def USING (indicator_id)
JOIN dim_vintage v USING (vintage);

-- Tracts whose boundaries are essentially the same in 2010 and 2020: land overlap is at least
-- 99 percent of both tracts and the pairing is one-to-one. Only these are compared across
-- vintages without re-allocating counts.
CREATE OR REPLACE VIEW v_stable_tract AS
WITH p AS (
  SELECT *, aland_overlap::DOUBLE / aland_2010 AS s10, aland_overlap::DOUBLE / aland_2020 AS s20
  FROM xwalk_tract_2010_2020 WHERE aland_2010 > 0 AND aland_2020 > 0
), sig AS (SELECT * FROM p WHERE s10 > 0.01 AND s20 > 0.01)
SELECT p.geoid_2010, p.geoid_2020, p.s10 AS share_of_2010, p.s20 AS share_of_2020
FROM p
WHERE p.s10 >= 0.99 AND p.s20 >= 0.99
  AND (SELECT count(*) FROM sig WHERE sig.geoid_2010 = p.geoid_2010) = 1
  AND (SELECT count(*) FROM sig WHERE sig.geoid_2020 = p.geoid_2020) = 1;

-- Change between the two vintages for stable tracts. The MOE of a difference of two
-- independent estimates is sqrt(moe1^2 + moe2^2). A change is "distinguishable" when
-- |change| exceeds that MOE. Dollar indicators are compared in 2024 dollars.
CREATE OR REPLACE VIEW v_change_stable AS
SELECT s.geoid_2010, s.geoid_2020, a.indicator_id,
       a.value_2024usd AS value_2013_2017, b.value_2024usd AS value_2020_2024,
       b.value_2024usd - a.value_2024usd AS change,
       sqrt(a.moe_2024usd^2 + b.moe_2024usd^2) AS change_moe,
       abs(b.value_2024usd - a.value_2024usd) > sqrt(a.moe_2024usd^2 + b.moe_2024usd^2) AS distinguishable
FROM v_stable_tract s
JOIN v_indicator_adj a ON a.vintage = '2013-2017' AND a.geo_level = 'tract' AND a.geoid = s.geoid_2010
JOIN v_indicator_adj b ON b.vintage = '2020-2024' AND b.geo_level = 'tract' AND b.geoid = s.geoid_2020
                      AND b.indicator_id = a.indicator_id
WHERE a.value IS NOT NULL AND b.value IS NOT NULL
  AND a.moe_2024usd IS NOT NULL AND b.moe_2024usd IS NOT NULL;
