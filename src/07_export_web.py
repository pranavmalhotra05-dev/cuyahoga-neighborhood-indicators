"""Export static data for the web viewer into web/data/.

Writes:
  tracts_2010.geojson, tracts_2020.geojson   simplified tract polygons (EPSG:4326, 5 decimals)
  indicators.json                            indicator metadata, per-vintage tract values, county totals,
                                             data dictionary, ACS table IDs and source note

Run: python -I src/07_export_web.py
"""
import datetime
import json
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import shapely
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent.parent
TIGER = ROOT / "data_raw" / "tiger"
OUT = ROOT / "web" / "data"
DB = ROOT / "data" / "cuyahoga.duckdb"
COUNTY = "035"
# Simplification tolerance in metres, applied in a projected CRS (UTM zone 17N).
TOLERANCE_M = 12.0
DECIMALS = 5
TRACT_FILES = {2010: "tl_2017_39_tract.zip", 2020: "tl_2024_39_tract.zip"}
ROUND_BY_KIND = {"count": 0, "rate": 2, "median_dollars": 0, "median_other": 1}


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], DECIMALS), round(obj[1], DECIMALS)]
        return [round_coords(o) for o in obj]
    return obj


def export_tracts(tract_vintage):
    g = gpd.read_file(f"zip://{TIGER / TRACT_FILES[tract_vintage]}")
    g = g[g["COUNTYFP"] == COUNTY].copy()
    n_all = len(g)
    water_only = g[g["ALAND"].astype("int64") == 0]
    g = g[g["ALAND"].astype("int64") > 0].copy()
    g = g.to_crs(32617)
    try:
        simp = shapely.coverage_simplify(g.geometry.values, TOLERANCE_M)
        method = "coverage_simplify"
    except Exception:
        simp = g.geometry.simplify(TOLERANCE_M, preserve_topology=True).values
        method = "simplify(preserve_topology)"
    g = g.set_geometry(gpd.GeoSeries(simp, index=g.index, crs=32617)).to_crs(4326)
    feats = []
    for geoid, name, geom in sorted(zip(g["GEOID"], g["NAMELSAD"], g.geometry)):
        gj = mapping(geom)
        feats.append({"type": "Feature",
                      "properties": {"GEOID": geoid, "NAMELSAD": name},
                      "geometry": {"type": gj["type"], "coordinates": round_coords(gj["coordinates"])}})
    path = OUT / f"tracts_{tract_vintage}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")),
                    encoding="utf-8")
    return path, n_all, list(water_only["GEOID"]), method


def clean(x, nd):
    if x is None or x != x:
        return None
    return int(round(x)) if nd == 0 else round(float(x), nd)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    water_dropped = {}
    for tv in (2010, 2020):
        path, n_all, water, method = export_tracts(tv)
        water_dropped[tv] = water
        report.append((path, f"{n_all} tracts in county, {len(water)} water-only dropped {water}, {method}"))

    con = duckdb.connect(str(DB), read_only=True)
    ind = con.execute("""
        SELECT d.indicator_id, d.name, d.kind, d.unit, d.higher_is, d.theme, d.definition,
               (SELECT list(DISTINCT v.table_id ORDER BY v.table_id)
                FROM indicator_cell c JOIN dim_variable v USING (variable)
                WHERE c.indicator_id = d.indicator_id) AS tables
        FROM indicator_def d ORDER BY d.theme, d.indicator_id""").fetchall()
    kinds = {r[0]: r[2] for r in ind}
    indicators = [{"id": r[0], "name": r[1], "kind": r[2], "unit": r[3], "higher_is": r[4],
                   "theme": r[5], "definition": r[6], "tables": r[7]} for r in ind]

    vint = con.execute("SELECT vintage, end_year, tract_vintage, dollar_year FROM dim_vintage ORDER BY vintage").fetchall()
    vintages = []
    data, county, names = {}, {}, {}
    for v, end_year, tv, dollar_year in vint:
        rows = con.execute("""SELECT indicator_id, geoid, value, moe, reliability FROM v_indicator
                              WHERE vintage = ? AND geo_level = 'tract' ORDER BY indicator_id, geoid""", [v]).fetchall()
        d = {}
        for iid, geoid, val, moe, rel in rows:
            nd = ROUND_BY_KIND[kinds[iid]]
            d.setdefault(iid, {})[geoid] = [clean(val, nd), clean(moe, nd), rel]
        data[v] = d
        crow = con.execute("""SELECT indicator_id, value, moe, reliability FROM v_indicator
                              WHERE vintage = ? AND geo_level = 'county' ORDER BY indicator_id""", [v]).fetchall()
        county[v] = {iid: [clean(val, ROUND_BY_KIND[kinds[iid]]), clean(moe, ROUND_BY_KIND[kinds[iid]]), rel]
                     for iid, val, moe, rel in crow}
        n_tr = con.execute("SELECT count(*) FROM dim_tract WHERE tract_vintage = ?", [tv]).fetchone()[0]
        vintages.append({"id": v, "end_year": end_year, "tract_vintage": tv, "dollar_year": dollar_year,
                         "tract_file": f"data/tracts_{tv}.geojson", "n_tracts": n_tr})
        names[str(tv)] = {g: n for g, n in con.execute(
            "SELECT geoid, name FROM dim_tract WHERE tract_vintage = ? ORDER BY geoid", [tv]).fetchall()}
    n_stable = con.execute("SELECT count(*) FROM v_stable_tract").fetchone()[0]
    fact_rows = con.execute("SELECT count(*) FROM fact_acs").fetchone()[0]
    con.close()

    meta = {
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": ("American Community Survey 5-year estimates, U.S. Census Bureau (summary file tables). "
                   "Tract boundaries: Census TIGER/Line 2017 (2010 tracts) and 2024 (2020 tracts). "
                   "County: Cuyahoga County, Ohio (FIPS 39035)."),
        "acs_tables": sorted({t for i in indicators for t in i["tables"]}),
        "vintages": vintages,
        "stable_tracts": n_stable,
        "fact_rows": fact_rows,
        "dropped_water_only_tracts": {str(k): v for k, v in water_dropped.items()},
        "moe_level_percent": 90,
        "reliability_classes": [
            {"id": "high", "label": "High", "rule": "coefficient of variation below 15 percent"},
            {"id": "medium", "label": "Medium", "rule": "coefficient of variation 15 to 30 percent"},
            {"id": "low", "label": "Low", "rule": "coefficient of variation above 30 percent"},
            {"id": "zero_estimate", "label": "Zero estimate", "rule": "estimate is zero, so a coefficient of variation is undefined"},
            {"id": "no_moe", "label": "No MOE", "rule": "an estimate exists but the Census Bureau published no margin of error"},
            {"id": "unavailable", "label": "Unavailable", "rule": "estimate suppressed, censored or not computable"},
        ],
        "dollars_note": "Dollar indicators are in the dollars of each vintage end year (nominal), not inflation adjusted.",
    }
    dictionary = [
        {"field": "value", "description": "Indicator estimate. Rates are percent (0 to 100), counts are people or households, medians are in the unit shown for the indicator."},
        {"field": "moe", "description": "90 percent margin of error of the value, in the same unit, derived with the Census Bureau ACS handbook formulas for sums and proportions."},
        {"field": "cv", "description": "Coefficient of variation = (MOE / 1.645) / value. Used to classify reliability. Not exported per tract to keep the file small."},
        {"field": "reliability", "description": "Class from the CV: high below 0.15, medium 0.15 to 0.30, low above 0.30, plus zero_estimate, no_moe and unavailable."},
        {"field": "geoid", "description": "11 character census tract identifier: state (2), county (3), tract (6). Identifiers are only comparable within one tract geography (2010 or 2020)."},
        {"field": "data[vintage][indicator][geoid]", "description": "Array [value, moe, reliability]. JSON null means the value or margin of error is not available."},
    ]
    payload = {"meta": meta, "indicators": indicators, "county": county, "tract_names": names,
               "dictionary": dictionary, "data": data}
    p = OUT / "indicators.json"
    p.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    report.append((p, f"{len(indicators)} indicators, {len(vintages)} vintages"))

    for path, note in report:
        print(f"{path.relative_to(ROOT).as_posix():40} {path.stat().st_size / 1024:9.1f} KB  {note}")
    big = [p for p, _ in report if p.suffix == ".geojson" and p.stat().st_size > 1.2e6]
    if big:
        print("WARNING: tract file larger than 1.2 MB:", big, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
