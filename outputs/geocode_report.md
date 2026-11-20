# Geocoding report

Source: NCES CCD school directory 2024 (Urban Institute Education Data API), retrieved 2026-11-20.

Rows returned for Ohio (fips=39): 3611 of 3611 (next page: None).
Rows with county_code 39035 (Cuyahoga): 345. Years present: [2024].
school_status counts (1 open, 2 closed, 3 new, other values per CCD codes): {1: 340, 2: 3, 3: 2}.
Open schools with a street address: 340.
Sample size: 300 (pandas random_state=42).

## One-line endpoint demonstration

| Input | Matched | 2020 tract GEOID |
|---|---|---|
| 4430 State Rd, Cleveland, OH 44109 | 4430 STATE RD, CLEVELAND, OH, 44109 | 39035106600 |
| 4901 Galaxy Pkwy Ste L, Cleveland, OH 44128 | 4901 GALAXY PKWY, CLEVELAND, OH, 44128 | 39035188107 |
| 6000 S Marginal Rd, Cleveland, OH 44103 | 6000 S MARGINAL RD, CLEVELAND, OH, 44103 | 39035111202 |
| 3122 Euclid Ave, Cleveland, OH 44115 | 3122 EUCLID AVE, CLEVELAND, OH, 44115 | 39035108701 |
| 11327 Shaker Blvd Ste 200 E., Cleveland, OH 44104 | 11327 SHAKER BLVD, CLEVELAND, OH, 44104 | 39035198600 |

## Batch geocoder result

Endpoint: https://geocoding.geo.census.gov/geocoder/geographies/addressbatch, benchmark Public_AR_Current, vintage Census2020_Current. Rows submitted: 300; rows returned: 300.

| Match status | Count | Share of sample |
|---|---|---|
| Match-Exact | 274 | 91.3 percent |
| Match-Non_Exact | 21 | 7.0 percent |
| No_Match | 5 | 1.7 percent |

Matched (exact plus non-exact): 295 of 300 = 98.3 percent. Ties: 0. No match: 5. No response row: 0.

## Tract assignment of matched points

Geocoder-returned tract equals the 2020 tract found by spatial join of the geocoded point: 295 of 295 = 100.0 percent.
Matched points with no 2020 tract found by spatial join: 0.
Matched points with no 2010 tract found by spatial join: 0.
Matched points whose geocoder county is not Cuyahoga: 0.

Matched points whose 2010 tract GEOID equals the 2020 geocoder tract GEOID (same code in both vintages): 253 of 295.

## Accuracy check against the source coordinates

The CCD supplies its own latitude and longitude for each school. Each source coordinate was placed in a 2020 tract by spatial join and compared with the tract the Census geocoder returned for the address.

Matched rows with source coordinates: 295. Same tract: 289 = 98.0 percent. Different tract: 6.
- Match-Exact: 270 of 274 same tract (98.5 percent).
- Match-Non_Exact: 19 of 21 same tract (90.5 percent).
Distance between geocoder point and source coordinate (metres): median 95, 90th percentile 268, maximum 9049.

Different-tract rows:

| Name | Input address | Match type | Geocoder tract | Source-coordinate tract | Distance m |
|---|---|---|---|---|---|
| Facing History High School@Charles Mooney | 3202 W 30th St, Cleveland, OH 44109 | Match-Exact | 39035197600 | 39035106800 | 3658 |
| John Adams College & Career Academy | 3817 Martin Luther King Jr Dr, Cleveland, OH 44105 | Match-Non_Exact | 39035108201 | 39035121100 | 9049 |
| Cleveland Metro Remote School K-12 | 3817 Martin Luther King Jr Dr, Cleveland, OH 44105 | Match-Non_Exact | 39035108201 | 39035121100 | 9049 |
| Greenbriar Middle School | 11810 Huffman Rd, Parma, OH 44130 | Match-Exact | 39035178102 | 39035177101 | 348 |
| Warrensville Heights Middle School | 23401 Emery Rd, Warrensville Heights, OH 44128 | Match-Exact | 39035198300 | 39035197000 | 1713 |
| Ballard Brady Middle School | 32000 Chagrin Blvd, Pepper Pike, OH 44124 | Match-Exact | 39035179102 | 39035196300 | 720 |

## Failures

Not matched: 5 of 300.
Of these, street contains a PO Box: 0; street does not start with a house number: 0.

| Name | Input address | Status |
|---|---|---|
| Constellation Schools: Parma Community | 7667 Day Dr Fl 1ST, Parma, OH 44129 | No_Match |
| Boulevard Elementary School | 1749 Lee Rd, Cleveland Heights, OH 44118 | No_Match |
| Lakewood High School | 14100 Franklin Blvd, Lakewood, OH 44107 | No_Match |
| Maple Heights High School | 1 Mustang Way, Maple Heights, OH 44137 | No_Match |
| Bedford High School | 481 Northfield Rd, Bedford, OH 44146 | No_Match |

## Database

geocode_sample rows loaded: 300.
Tracts containing at least one geocoded point: 191. With poverty_rate value: 191. With median_hh_income value: 187.
Mean poverty rate over geocoded tracts (each tract once): 17.7 percent; weighted by points: 18.6 percent.
