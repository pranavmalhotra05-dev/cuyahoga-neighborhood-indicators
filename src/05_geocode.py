"""Geocode a sample of public school addresses in Cuyahoga County with the U.S. Census Geocoder,
assign tracts, check them against the source coordinates, and load data/cuyahoga.duckdb
(geocode_sample only).

Source: NCES Common Core of Data school directory through the Urban Institute Education Data API.
Run: python -I src/05_geocode.py
"""
import csv
import io
import time
from datetime import date
from pathlib import Path
import duckdb
import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
TIGER = ROOT / "data_raw" / "tiger"
DB = ROOT / "data" / "cuyahoga.duckdb"
YEAR = 2024
SRC_URL = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{YEAR}/?fips=39"
SRC_LABEL = f"NCES CCD school directory {YEAR} (Urban Institute Education Data API)"
BATCH_URL = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
BENCHMARK, VINTAGE = "Public_AR_Current", "Census2020_Current"
N_SAMPLE, SEED = 300, 42
UA = {"User-Agent": "neighborhood-indicators-portfolio/1.0"}

out = []


def say(line=""):
    print(line)
    out.append(line)


def with_retry(fn, what, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # network or HTTP failure
            wait = 2 ** i * 2
            print(f"  {what}: attempt {i + 1} failed ({type(e).__name__}: {str(e)[:120]}); waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"{what} failed after {tries} attempts")


def get_schools():
    def f():
        r = requests.get(SRC_URL, headers=UA, timeout=180)
        r.raise_for_status()
        return r.json()
    d = with_retry(f, "school directory download")
    return pd.DataFrame(d["results"]), d["count"], d["next"]


def batch_geocode(df):
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    for r in df.itertuples():
        w.writerow([r.address_id, r.street, r.city, "OH", r.zip])
    payload = buf.getvalue().encode("utf-8")

    def f():
        r = requests.post(BATCH_URL, headers=UA, timeout=600,
                          files={"addressFile": ("addresses.csv", payload, "text/csv")},
                          data={"benchmark": BENCHMARK, "vintage": VINTAGE})
        r.raise_for_status()
        return r.text
    text = with_retry(f, "batch geocode")
    cols = ["address_id", "geocoder_input", "status", "match_type", "matched_address", "coords",
            "tigerline_id", "side", "state_fips", "county_fips", "tract_code", "block"]
    rows = []
    for rec in csv.reader(io.StringIO(text)):
        if not rec:
            continue
        rows.append((rec + [""] * len(cols))[:len(cols)])
    res = pd.DataFrame(rows, columns=cols)
    res["address_id"] = res["address_id"].astype(int)
    return res


def oneline(address):
    def f():
        r = requests.get(ONELINE_URL, headers=UA, timeout=60,
                         params={"address": address, "benchmark": BENCHMARK, "vintage": VINTAGE, "format": "json"})
        r.raise_for_status()
        return r.json()
    return with_retry(f, "one-line geocode", tries=3)


def main():
    today = date.today().isoformat()
    say("# Geocoding report")
    say()
    df, total_ohio, next_page = get_schools()
    say(f"Source: {SRC_LABEL}, retrieved {today}.")
    say()
    say(f"Rows returned for Ohio (fips=39): {len(df)} of {total_ohio} (next page: {next_page}).")
    cy = df[df["county_code"] == "39035"].copy()
    say(f"Rows with county_code 39035 (Cuyahoga): {len(cy)}. Years present: {sorted(cy['year'].unique().tolist())}.")
    status_counts = cy["school_status"].value_counts().sort_index().to_dict()
    say(f"school_status counts (1 open, 2 closed, 3 new, other values per CCD codes): {status_counts}.")
    n_all = len(cy)
    cy = cy[cy["school_status"] == 1]
    cy = cy[cy["street_location"].notna() & (cy["street_location"].str.strip() != "")]
    say(f"Open schools with a street address: {len(cy)}.")
    cy = cy.sort_values("ncessch").reset_index(drop=True)
    n = min(N_SAMPLE, len(cy))
    samp = cy.sample(n=n, random_state=SEED).sort_values("ncessch").reset_index(drop=True)
    say(f"Sample size: {n} (pandas random_state={SEED}).")
    say()
    samp["address_id"] = range(1, n + 1)
    samp["street"] = samp["street_location"].str.strip()
    samp["city"] = samp["city_location"].str.strip()
    samp["zip"] = samp["zip_location"].astype(str).str.strip().str[:5]
    samp["input_address"] = samp["street"] + ", " + samp["city"] + ", OH " + samp["zip"]

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "geocode_source.md").write_text("\n".join([
        "# Geocoding address source", "",
        f"- Dataset: NCES Common Core of Data (CCD), public school directory, file year {YEAR}.",
        "- Access: Urban Institute Education Data API (open, no key).",
        f"- Exact URL: {SRC_URL}",
        "- Filter applied locally: county_code == 39035 (the API ignores the county_code query parameter), "
        "school_status == 1 (open), street_location not empty.",
        f"- Retrieval date: {today}.",
        f"- Records returned for Ohio: {len(df)}. Cuyahoga records: {n_all}. After filters: {len(cy)}.",
        f"- Sample: {n} schools, pandas sample with random_state={SEED}, after sorting on NCESSCH.",
        "- Fields used: school_name, street_location, city_location, zip_location, latitude, longitude, ncessch.",
        "- Terms: public government data republished by the Urban Institute; cite NCES CCD and the Education Data Portal.",
        ""]), encoding="utf-8")

    say("## One-line endpoint demonstration")
    say()
    say("| Input | Matched | 2020 tract GEOID |")
    say("|---|---|---|")
    for a in samp["input_address"].head(5):
        try:
            j = oneline(a)
            mm = j["result"]["addressMatches"]
            if mm:
                g = mm[0]["geographies"]["Census Tracts"][0]["GEOID"]
                say(f"| {a} | {mm[0]['matchedAddress']} | {g} |")
            else:
                say(f"| {a} | no match | |")
        except Exception as e:
            say(f"| {a} | request failed: {type(e).__name__} | |")
    say()

    res = batch_geocode(samp)
    res["tract_geoid_geocoder"] = res["state_fips"] + res["county_fips"] + res["tract_code"]
    res.loc[res["status"] != "Match", "tract_geoid_geocoder"] = None
    ll = res["coords"].str.split(",", expand=True)
    res["lon"] = pd.to_numeric(ll[0], errors="coerce")
    res["lat"] = pd.to_numeric(ll[1], errors="coerce")
    m = samp.merge(res.drop(columns=["geocoder_input"]), on="address_id", how="left")
    m["match_status"] = m["status"].fillna("No_Response")
    m.loc[m["status"] == "Match", "match_status"] = "Match-" + m["match_type"]

    say("## Batch geocoder result")
    say()
    say(f"Endpoint: {BATCH_URL}, benchmark {BENCHMARK}, vintage {VINTAGE}. Rows submitted: {len(samp)}; rows returned: {len(res)}.")
    say()
    say("| Match status | Count | Share of sample |")
    say("|---|---|---|")
    for k, v in m["match_status"].value_counts().items():
        say(f"| {k} | {v} | {100 * v / n:.1f} percent |")
    matched = m[m["status"] == "Match"].copy()
    say()
    say(f"Matched (exact plus non-exact): {len(matched)} of {n} = {100 * len(matched) / n:.1f} percent. "
        f"Ties: {int((m['status'] == 'Tie').sum())}. No match: {int((m['status'] == 'No_Match').sum())}. "
        f"No response row: {int(m['status'].isna().sum())}.")
    say()

    t20 = gpd.read_file(f"zip://{TIGER / 'tl_2024_39_tract.zip'}")
    t20 = t20[t20["COUNTYFP"] == "035"][["GEOID", "geometry"]]
    t10 = gpd.read_file(f"zip://{TIGER / 'tl_2017_39_tract.zip'}")
    t10 = t10[t10["COUNTYFP"] == "035"][["GEOID", "geometry"]]

    def sj(lon, lat, ids, polys, name):
        pts = gpd.GeoDataFrame({"address_id": list(ids)}, geometry=gpd.points_from_xy(list(lon), list(lat)), crs="EPSG:4269")
        j = gpd.sjoin(pts, polys.rename(columns={"GEOID": name}), how="left", predicate="within")
        return j.drop_duplicates("address_id").set_index("address_id")[name]

    s20 = sj(matched["lon"], matched["lat"], matched["address_id"], t20, "sj_tract_2020")
    s10 = sj(matched["lon"], matched["lat"], matched["address_id"], t10, "sj_tract_2010")
    matched = matched.set_index("address_id").join(s20).join(s10).reset_index()
    agree = matched["tract_geoid_geocoder"] == matched["sj_tract_2020"]
    say("## Tract assignment of matched points")
    say()
    say(f"Geocoder-returned tract equals the 2020 tract found by spatial join of the geocoded point: "
        f"{int(agree.sum())} of {len(matched)} = {100 * agree.mean():.1f} percent.")
    say(f"Matched points with no 2020 tract found by spatial join: {int(matched['sj_tract_2020'].isna().sum())}.")
    say(f"Matched points with no 2010 tract found by spatial join: {int(matched['sj_tract_2010'].isna().sum())}.")
    outside = matched[~matched["tract_geoid_geocoder"].str.startswith("39035")]
    say(f"Matched points whose geocoder county is not Cuyahoga: {len(outside)}.")
    dis = matched[~agree]
    if len(dis):
        say()
        say("Disagreements:")
        say()
        say("| Name | Geocoder tract | Spatial join tract |")
        say("|---|---|---|")
        for r in dis.head(10).itertuples():
            say(f"| {r.school_name} | {r.tract_geoid_geocoder} | {r.sj_tract_2020} |")
    say()
    xw = matched[matched["sj_tract_2010"].notna()]
    say(f"Matched points whose 2010 tract GEOID equals the 2020 geocoder tract GEOID (same code in both vintages): "
        f"{int((xw['sj_tract_2010'] == xw['tract_geoid_geocoder']).sum())} of {len(xw)}.")
    say()

    has_src = matched[matched["latitude"].notna() & matched["longitude"].notna()].copy()
    ssj = sj(has_src["longitude"], has_src["latitude"], has_src["address_id"], t20, "src_tract_2020")
    has_src = has_src.set_index("address_id").join(ssj).reset_index(drop=True) if False else \
        has_src.merge(ssj.reset_index(), on="address_id", how="left")
    eq = has_src["tract_geoid_geocoder"] == has_src["src_tract_2020"]
    say("## Accuracy check against the source coordinates")
    say()
    say("The CCD supplies its own latitude and longitude for each school. Each source coordinate was placed in a 2020 tract "
        "by spatial join and compared with the tract the Census geocoder returned for the address.")
    say()
    say(f"Matched rows with source coordinates: {len(has_src)}. Same tract: {int(eq.sum())} = {100 * eq.mean():.1f} percent. "
        f"Different tract: {int((~eq).sum())}.")
    for k, g in has_src.assign(eq=eq).groupby("match_status"):
        say(f"- {k}: {int(g['eq'].sum())} of {len(g)} same tract ({100 * g['eq'].mean():.1f} percent).")
    a = gpd.GeoSeries(gpd.points_from_xy(has_src["lon"], has_src["lat"]), crs="EPSG:4269").to_crs("EPSG:5070")
    b = gpd.GeoSeries(gpd.points_from_xy(has_src["longitude"], has_src["latitude"]), crs="EPSG:4269").to_crs("EPSG:5070")
    dist = pd.Series(a.distance(b, align=False).to_numpy(), index=has_src.index)
    say(f"Distance between geocoder point and source coordinate (metres): median {dist.median():.0f}, "
        f"90th percentile {dist.quantile(0.9):.0f}, maximum {dist.max():.0f}.")
    bad = has_src[~eq]
    if len(bad):
        say()
        say("Different-tract rows:")
        say()
        say("| Name | Input address | Match type | Geocoder tract | Source-coordinate tract | Distance m |")
        say("|---|---|---|---|---|---|")
        for i, r in bad.head(12).iterrows():
            say(f"| {r['school_name']} | {r['input_address']} | {r['match_status']} | {r['tract_geoid_geocoder']} "
                f"| {r['src_tract_2020']} | {dist.loc[i]:.0f} |")
    say()

    fails = m[m["status"] != "Match"]
    say("## Failures")
    say()
    say(f"Not matched: {len(fails)} of {n}.")
    if len(fails):
        po = fails["street"].str.contains(r"P\.?\s*O\.?\s*Box", case=False, regex=True).sum()
        nonum = (~fails["street"].str.match(r"^\d")).sum()
        say(f"Of these, street contains a PO Box: {int(po)}; street does not start with a house number: {int(nonum)}.")
        say()
        say("| Name | Input address | Status |")
        say("|---|---|---|")
        for r in fails.head(25).itertuples():
            say(f"| {r.school_name} | {r.input_address} | {r.match_status} |")
    say()

    raw = m[["address_id", "ncessch", "school_name", "input_address", "latitude", "longitude",
             "status", "match_type", "matched_address", "coords", "tigerline_id", "side",
             "state_fips", "county_fips", "tract_code", "block"]].rename(
        columns={"latitude": "source_lat", "longitude": "source_lon", "status": "geocoder_status",
                 "match_type": "geocoder_match_type"})
    raw.to_csv(ROOT / "data" / "geocode_results.csv", index=False, encoding="utf-8")

    final = m[["address_id", "school_name", "input_address", "match_status", "matched_address", "lon", "lat",
               "tract_geoid_geocoder"]].merge(matched[["address_id", "sj_tract_2010"]], on="address_id", how="left")
    tbl = pd.DataFrame({
        "address_id": final["address_id"], "source": SRC_LABEL, "name": final["school_name"],
        "input_address": final["input_address"], "match_status": final["match_status"],
        "matched_address": final["matched_address"].replace("", None), "lon": final["lon"], "lat": final["lat"],
        "tract_geoid_2020": final["tract_geoid_geocoder"], "tract_geoid_2010": final["sj_tract_2010"]})
    con = duckdb.connect(str(DB))
    con.execute("DELETE FROM geocode_sample")
    con.execute("INSERT INTO geocode_sample SELECT * FROM tbl")
    say("## Database")
    say()
    say(f"geocode_sample rows loaded: {con.execute('SELECT count(*) FROM geocode_sample').fetchone()[0]}.")

    t = con.execute("""
        WITH g AS (SELECT tract_geoid_2020 AS geoid, count(*) AS n_points, string_agg(name, '; ' ORDER BY name) AS names
                   FROM geocode_sample WHERE tract_geoid_2020 IS NOT NULL GROUP BY 1),
             p AS (SELECT geoid, value AS poverty_rate, moe AS poverty_rate_moe FROM v_indicator
                   WHERE vintage = '2020-2024' AND geo_level = 'tract' AND indicator_id = 'poverty_rate'),
             i AS (SELECT geoid, value AS median_hh_income, moe AS median_hh_income_moe FROM v_indicator
                   WHERE vintage = '2020-2024' AND geo_level = 'tract' AND indicator_id = 'median_hh_income')
        SELECT g.geoid, g.n_points, p.poverty_rate, p.poverty_rate_moe, i.median_hh_income, i.median_hh_income_moe, g.names
        FROM g LEFT JOIN p USING (geoid) LEFT JOIN i USING (geoid) ORDER BY g.geoid""").df()
    (ROOT / "outputs").mkdir(exist_ok=True)
    t.to_csv(ROOT / "outputs" / "geocode_by_tract.csv", index=False, encoding="utf-8")
    ok = t["poverty_rate"].notna()
    say(f"Tracts containing at least one geocoded point: {len(t)}. With poverty_rate value: {int(ok.sum())}. "
        f"With median_hh_income value: {int(t['median_hh_income'].notna().sum())}.")
    say(f"Mean poverty rate over geocoded tracts (each tract once): {t['poverty_rate'].mean():.1f} percent; "
        f"weighted by points: {(t.loc[ok, 'poverty_rate'] * t.loc[ok, 'n_points']).sum() / t.loc[ok, 'n_points'].sum():.1f} percent.")
    con.close()
    (ROOT / "outputs" / "geocode_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
