-- Relational, longitudinal tract-by-vintage design.
-- One fact row per (vintage, geography, ACS cell). Tract identity is only stable within a
-- tract geography vintage (2010 or 2020), so dim_tract is keyed by (tract_vintage, geoid).

CREATE OR REPLACE TABLE dim_vintage (
    vintage        VARCHAR PRIMARY KEY,      -- ACS 5-year period, e.g. 2020-2024
    end_year       INTEGER NOT NULL,
    tract_vintage  INTEGER NOT NULL,         -- census tract geography: 2010 or 2020
    dollar_year    INTEGER NOT NULL,         -- price year of dollar-valued cells
    cpi_u          DOUBLE  NOT NULL          -- CPI-U annual average for dollar_year
);

CREATE OR REPLACE TABLE dim_tract (
    tract_vintage  INTEGER NOT NULL,
    geoid          VARCHAR NOT NULL,         -- 11 characters: state 2, county 3, tract 6
    county_fips    VARCHAR NOT NULL,
    tract_code     VARCHAR NOT NULL,
    name           VARCHAR,
    aland_m2       BIGINT,
    awater_m2      BIGINT,
    intpt_lat      DOUBLE,
    intpt_lon      DOUBLE,
    PRIMARY KEY (tract_vintage, geoid)
);

CREATE OR REPLACE TABLE dim_variable (
    variable    VARCHAR PRIMARY KEY,         -- e.g. B17001_002
    table_id    VARCHAR NOT NULL,
    line        INTEGER NOT NULL,
    label       VARCHAR,
    table_title VARCHAR,
    universe    VARCHAR
);

CREATE OR REPLACE TABLE fact_acs (
    vintage    VARCHAR NOT NULL REFERENCES dim_vintage(vintage),
    geo_level  VARCHAR NOT NULL CHECK (geo_level IN ('tract', 'county')),
    geoid      VARCHAR NOT NULL,
    variable   VARCHAR NOT NULL REFERENCES dim_variable(variable),
    estimate   DOUBLE,                       -- NULL when suppressed or unavailable
    moe        DOUBLE,                       -- 90 percent margin of error, NULL when unavailable
    flag       VARCHAR,                      -- Census sentinel meaning, see src/01_ingest.py
    PRIMARY KEY (vintage, geo_level, geoid, variable)
);

CREATE OR REPLACE TABLE xwalk_tract_2010_2020 (
    geoid_2010     VARCHAR NOT NULL,
    geoid_2020     VARCHAR NOT NULL,
    aland_2010     BIGINT,
    aland_2020     BIGINT,
    aland_overlap  BIGINT,
    PRIMARY KEY (geoid_2010, geoid_2020)
);

CREATE OR REPLACE TABLE indicator_def (
    indicator_id  VARCHAR PRIMARY KEY,
    name          VARCHAR NOT NULL,
    kind          VARCHAR NOT NULL CHECK (kind IN ('count', 'rate', 'median_dollars', 'median_other')),
    unit          VARCHAR NOT NULL,
    higher_is     VARCHAR NOT NULL,          -- 'worse', 'better' or 'neutral', for map colour direction
    theme         VARCHAR NOT NULL,
    definition    VARCHAR NOT NULL
);

-- Which ACS cells form the numerator and the denominator of an indicator.
CREATE OR REPLACE TABLE indicator_cell (
    indicator_id  VARCHAR NOT NULL REFERENCES indicator_def(indicator_id),
    role          VARCHAR NOT NULL CHECK (role IN ('num', 'den')),
    variable      VARCHAR NOT NULL REFERENCES dim_variable(variable),
    PRIMARY KEY (indicator_id, role, variable)
);

-- Geocoded public addresses and their tract assignment (filled by src/05_geocode.py).
CREATE OR REPLACE TABLE geocode_sample (
    address_id        INTEGER PRIMARY KEY,
    source            VARCHAR,
    name              VARCHAR,
    input_address     VARCHAR,
    match_status      VARCHAR,
    matched_address   VARCHAR,
    lon               DOUBLE,
    lat               DOUBLE,
    tract_geoid_2020  VARCHAR,
    tract_geoid_2010  VARCHAR
);
