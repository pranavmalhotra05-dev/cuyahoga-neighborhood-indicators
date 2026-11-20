# Spatial checks

All numbers below are printed by src/04_spatial_checks.py.

## (a) TIGER tract counts and CRS

| Layer | File | Ohio tracts | Cuyahoga tracts | dim_tract rows | CRS | Invalid geometries | Duplicate GEOIDs |
|---|---|---|---|---|---|---|---|
| 2010 tracts | tl_2017_39_tract.zip | 2952 | 447 | 447 | EPSG:4269 | 0 | 0 |
| 2020 tracts | tl_2024_39_tract.zip | 3168 | 428 | 428 | EPSG:4269 | 0 | 0 |

County layer: 3235 counties, Cuyahoga rows found 1, CRS EPSG:4269.

## (b) Stable tract cross-check (2010 vs 2020 tracts)

Overlay in EPSG:5070 on total polygon area (land plus water, because TIGER polygons carry no separate land geometry). Rule is the same as v_stable_tract: overlap at least 99% of both tracts and one-to-one among pieces larger than 1%.

Overlay pieces with positive area: 2136.

v_stable_tract (Census land-area relationship file): 324 tracts.

| Threshold on geometry area | Stable pairs (overlay) | In both | Only overlay | Only SQL view | Jaccard agreement |
|---|---|---|---|---|---|
| 0.99 | 323 | 319 | 4 | 5 | 0.973 |
| 0.98 | 343 | 321 | 22 | 3 | 0.928 |
| 0.95 | 348 | 321 | 27 | 3 | 0.915 |

Pairs that differ at the 0.99 threshold (first 25):

| geoid_2010 | geoid_2020 | In overlay set | In SQL set | Geometry share of 2010 | Geometry share of 2020 | Land share of 2010 | Land share of 2020 |
|---|---|---|---|---|---|---|---|
| 39035114600 | 39035114600 | False | True | 0.9864 | 0.9950 | 1.0000 | 0.9994 |
| 39035117101 | 39035117101 | True | False | 0.9974 | 0.9913 | 0.9995 | 0.9849 |
| 39035134203 | 39035134203 | False | True | 0.9726 | 0.9937 | 0.9965 | 1.0000 |
| 39035134205 | 39035134205 | False | True | 0.9859 | 0.9911 | 1.0000 | 0.9910 |
| 39035171103 | 39035171103 | True | False | 1.0000 | 1.0000 | 0.9742 | 1.0000 |
| 39035171104 | 39035171104 | True | False | 1.0000 | 1.0000 | 0.9876 | 1.0000 |
| 39035183605 | 39035183605 | False | True | 0.9854 | 1.0000 | 0.9931 | 1.0000 |
| 39035190502 | 39035190502 | False | True | 0.9904 | 0.9788 | 0.9970 | 0.9908 |
| 39035990000 | 39035990000 | True | False | 1.0000 | 0.9995 | n/a (no land) | n/a (no land) |

Result: at the 0.99 threshold the overlay finds 323 stable pairs against 324 in the SQL view; 319 are in both (97.3 percent of the union).

## (c) Internal point inside own tract polygon

TIGER INTPTLAT and INTPTLON (the Census internal point) are joined to the polygons with a spatial join (predicate within).

| Layer | Tracts | Internal points inside own tract | Not inside own tract | Inside a different tract | Inside no tract |
|---|---|---|---|---|---|
| 2010 tracts | 447 | 447 | 0 | 0 | 0 |
| 2020 tracts | 428 | 428 | 0 | 0 | 0 |

Internal points are chosen by the Census Bureau and are not guaranteed to be inside irregular tracts, so misses are possible on lakefront or non-convex tracts.
