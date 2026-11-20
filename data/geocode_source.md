# Geocoding address source

- Dataset: NCES Common Core of Data (CCD), public school directory, file year 2024.
- Access: Urban Institute Education Data API (open, no key).
- Exact URL: https://educationdata.urban.org/api/v1/schools/ccd/directory/2024/?fips=39
- Filter applied locally: county_code == 39035 (the API ignores the county_code query parameter), school_status == 1 (open), street_location not empty.
- Retrieval date: 2026-11-20.
- Records returned for Ohio: 3611. Cuyahoga records: 345. After filters: 340.
- Sample: 300 schools, pandas sample with random_state=42, after sorting on NCESSCH.
- Fields used: school_name, street_location, city_location, zip_location, latitude, longitude, ncessch.
- Terms: public government data republished by the Urban Institute; cite NCES CCD and the Education Data Portal.
