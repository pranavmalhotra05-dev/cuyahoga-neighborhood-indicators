-- 15 indicators. Numerator and denominator are sums of ACS cells; medians are single cells.
INSERT INTO indicator_def VALUES
('pop_total',         'Total population',                        'count',          'people',  'neutral', 'Population', 'B01003 line 1: total population.'),
('median_age',        'Median age',                              'median_other',   'years',   'neutral', 'Population', 'B01002 line 1: median age, both sexes.'),
('poverty_rate',      'Poverty rate',                            'rate',           'percent', 'worse',   'Income',     'People with income in the past 12 months below the federal poverty level divided by people for whom poverty status is determined (B17001 line 2 over line 1).'),
('median_hh_income',  'Median household income',                 'median_dollars', 'dollars', 'better',  'Income',     'B19013 line 1, in the dollars of the vintage end year. A column expressed in 2024 dollars with CPI-U is also provided.'),
('rent_burden_30',    'Rent burden (30 percent or more)',        'rate',           'percent', 'worse',   'Housing',    'Renter households paying 30 percent or more of income on gross rent, divided by renter households with a computed rent share (B25070 lines 7-10 over lines 2-10).'),
('rent_burden_50',    'Severe rent burden (50 percent or more)', 'rate',           'percent', 'worse',   'Housing',    'Renter households paying 50 percent or more of income on gross rent over renter households with a computed rent share (B25070 line 10 over lines 2-10).'),
('vacancy_rate',      'Housing vacancy rate',                    'rate',           'percent', 'worse',   'Housing',    'Vacant housing units divided by all housing units (B25002 line 3 over line 1).'),
('other_vacant',      'Other vacant units share',                'rate',           'percent', 'worse',   'Housing',    'Vacant units classified as other vacant (not for rent, for sale, seasonal or sold; often long-term abandoned) divided by all housing units (B25004 line 8 over B25002 line 1).'),
('renter_share',      'Renter-occupied share',                   'rate',           'percent', 'neutral', 'Housing',    'Renter-occupied housing units divided by occupied housing units (B25003 line 3 over line 1).'),
('median_home_value', 'Median home value',                       'median_dollars', 'dollars', 'better',  'Housing',    'B25077 line 1, median value of owner-occupied units, in the dollars of the vintage end year. An adjusted column is provided.'),
('no_vehicle',        'Households without a vehicle',            'rate',           'percent', 'worse',   'Mobility',   'Occupied housing units with no vehicle available divided by occupied housing units (B25044 lines 3 and 10 over line 1).'),
('no_hs_diploma',     'Adults without a high school diploma',    'rate',           'percent', 'worse',   'Education',  'People 25 and over whose highest attainment is below a regular diploma or GED, divided by people 25 and over (B15003 lines 2-16 over line 1).'),
('bachelors_plus',    'Adults with a bachelors degree or more',  'rate',           'percent', 'better',  'Education',  'People 25 and over with a bachelors, masters, professional or doctoral degree divided by people 25 and over (B15003 lines 22-25 over line 1).'),
('unemployment_rate', 'Unemployment rate',                       'rate',           'percent', 'worse',   'Work',       'Unemployed civilians divided by the civilian labor force (B23025 line 5 over line 3).'),
('single_parent',     'Single-parent family share',              'rate',           'percent', 'worse',   'Families',   'Family households with own children under 18 headed by a householder with no spouse present, divided by all family households with own children under 18 (B11003 lines 10 and 16 over lines 3, 10 and 16).');

INSERT INTO indicator_cell
SELECT * FROM (VALUES
 ('pop_total','num','B01003_001'),
 ('median_age','num','B01002_001'),
 ('median_hh_income','num','B19013_001'),
 ('median_home_value','num','B25077_001'),
 ('poverty_rate','num','B17001_002'), ('poverty_rate','den','B17001_001'),
 ('rent_burden_30','num','B25070_007'), ('rent_burden_30','num','B25070_008'),
 ('rent_burden_30','num','B25070_009'), ('rent_burden_30','num','B25070_010'),
 ('rent_burden_50','num','B25070_010'),
 ('vacancy_rate','num','B25002_003'), ('vacancy_rate','den','B25002_001'),
 ('other_vacant','num','B25004_008'), ('other_vacant','den','B25002_001'),
 ('renter_share','num','B25003_003'), ('renter_share','den','B25003_001'),
 ('no_vehicle','num','B25044_003'), ('no_vehicle','num','B25044_010'), ('no_vehicle','den','B25044_001'),
 ('bachelors_plus','num','B15003_022'), ('bachelors_plus','num','B15003_023'),
 ('bachelors_plus','num','B15003_024'), ('bachelors_plus','num','B15003_025'), ('bachelors_plus','den','B15003_001'),
 ('no_hs_diploma','den','B15003_001'),
 ('unemployment_rate','num','B23025_005'), ('unemployment_rate','den','B23025_003'),
 ('single_parent','num','B11003_010'), ('single_parent','num','B11003_016'),
 ('single_parent','den','B11003_003'), ('single_parent','den','B11003_010'), ('single_parent','den','B11003_016')
) t(indicator_id, role, variable);

INSERT INTO indicator_cell SELECT 'rent_burden_30', 'den', printf('B25070_%03d', i) FROM range(2, 11) r(i);
INSERT INTO indicator_cell SELECT 'rent_burden_50', 'den', printf('B25070_%03d', i) FROM range(2, 11) r(i);
INSERT INTO indicator_cell SELECT 'no_hs_diploma',  'num', printf('B15003_%03d', i) FROM range(2, 17) r(i);
