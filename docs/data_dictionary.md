# Data dictionary

## Tables

### dim_tract (875 rows)

| Column | Type |
|---|---|
| tract_vintage | INTEGER |
| geoid | VARCHAR |
| county_fips | VARCHAR |
| tract_code | VARCHAR |
| name | VARCHAR |
| aland_m2 | BIGINT |
| awater_m2 | BIGINT |
| intpt_lat | DOUBLE |
| intpt_lon | DOUBLE |

### dim_variable (157 rows)

| Column | Type |
|---|---|
| variable | VARCHAR |
| table_id | VARCHAR |
| line | INTEGER |
| label | VARCHAR |
| table_title | VARCHAR |
| universe | VARCHAR |

### dim_vintage (2 rows)

| Column | Type |
|---|---|
| vintage | VARCHAR |
| end_year | INTEGER |
| tract_vintage | INTEGER |
| dollar_year | INTEGER |
| cpi_u | DOUBLE |

### dq_results (47 rows)

| Column | Type |
|---|---|
| check_id | VARCHAR |
| description | VARCHAR |
| expected | VARCHAR |
| observed | VARCHAR |
| status | VARCHAR |

### fact_acs (137689 rows)

| Column | Type |
|---|---|
| vintage | VARCHAR |
| geo_level | VARCHAR |
| geoid | VARCHAR |
| variable | VARCHAR |
| estimate | DOUBLE |
| moe | DOUBLE |
| flag | VARCHAR |

### geocode_sample (0 rows)

| Column | Type |
|---|---|
| address_id | INTEGER |
| source | VARCHAR |
| name | VARCHAR |
| input_address | VARCHAR |
| match_status | VARCHAR |
| matched_address | VARCHAR |
| lon | DOUBLE |
| lat | DOUBLE |
| tract_geoid_2020 | VARCHAR |
| tract_geoid_2010 | VARCHAR |

### indicator_cell (66 rows)

| Column | Type |
|---|---|
| indicator_id | VARCHAR |
| role | VARCHAR |
| variable | VARCHAR |

### indicator_def (15 rows)

| Column | Type |
|---|---|
| indicator_id | VARCHAR |
| name | VARCHAR |
| kind | VARCHAR |
| unit | VARCHAR |
| higher_is | VARCHAR |
| theme | VARCHAR |
| definition | VARCHAR |

### xwalk_tract_2010_2020 (631 rows)

| Column | Type |
|---|---|
| geoid_2010 | VARCHAR |
| geoid_2020 | VARCHAR |
| aland_2010 | BIGINT |
| aland_2020 | BIGINT |
| aland_overlap | BIGINT |

## Views

- `v_change_stable`: geoid_2010, geoid_2020, indicator_id, value_2013_2017, value_2020_2024, change, change_moe, distinguishable
- `v_component`: vintage, geo_level, geoid, indicator_id, role, est, moe, n_cells, n_cells_with_estimate, n_cells_with_moe
- `v_indicator`: vintage, geo_level, geoid, indicator_id, value, moe, denominator, cv, reliability
- `v_indicator_adj`: vintage, geo_level, geoid, indicator_id, value, moe, denominator, cv, reliability, value_2024usd, moe_2024usd
- `v_stable_tract`: geoid_2010, geoid_2020, share_of_2010, share_of_2020
