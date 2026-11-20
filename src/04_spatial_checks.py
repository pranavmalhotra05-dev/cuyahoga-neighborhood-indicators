"""Spatial checks with GeoPandas: TIGER tract counts and CRS, an independent recomputation of the
2010-2020 stable-tract set by polygon overlay, and a centroid-in-polygon sanity check.
Writes outputs/spatial_checks.md.

Run: python -I src/04_spatial_checks.py
"""
from pathlib import Path
import duckdb
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TIGER = ROOT / "data_raw" / "tiger"
DB = ROOT / "data" / "cuyahoga.duckdb"
COUNTY = "035"
AREA_CRS = "EPSG:5070"  # NAD83 / Conus Albers, equal area
THRESH = 0.99           # same rule as v_stable_tract
SIG = 0.01

out = []


def say(line=""):
    print(line)
    out.append(line)


def load(zipname):
    g = gpd.read_file(f"zip://{TIGER / zipname}")
    return g


def main():
    say("# Spatial checks")
    say()
    say("All numbers below are printed by src/04_spatial_checks.py.")
    say()
    raw10, raw20 = load("tl_2017_39_tract.zip"), load("tl_2024_39_tract.zip")
    g10 = raw10[raw10["COUNTYFP"] == COUNTY].copy()
    g20 = raw20[raw20["COUNTYFP"] == COUNTY].copy()

    # (a) counts and CRS
    con = duckdb.connect(str(DB), read_only=True)
    db_counts = dict(con.execute("SELECT tract_vintage, count(*) FROM dim_tract GROUP BY 1").fetchall())
    say("## (a) TIGER tract counts and CRS")
    say()
    say("| Layer | File | Ohio tracts | Cuyahoga tracts | dim_tract rows | CRS | Invalid geometries | Duplicate GEOIDs |")
    say("|---|---|---|---|---|---|---|---|")
    for label, tv, raw, g, fn in (("2010 tracts", 2010, raw10, g10, "tl_2017_39_tract.zip"),
                                  ("2020 tracts", 2020, raw20, g20, "tl_2024_39_tract.zip")):
        say(f"| {label} | {fn} | {len(raw)} | {len(g)} | {db_counts.get(tv)} | {g.crs.to_string()} "
            f"| {int((~g.geometry.is_valid).sum())} | {int(g['GEOID'].duplicated().sum())} |")
    say()
    cty = gpd.read_file(f"zip://{TIGER / 'tl_2024_us_county.zip'}")
    c = cty[cty["GEOID"] == "39035"]
    say(f"County layer: {len(cty)} counties, Cuyahoga rows found {len(c)}, CRS {cty.crs.to_string()}.")
    say()

    # (b) stable tracts by overlay
    p10, p20 = g10.to_crs(AREA_CRS), g20.to_crs(AREA_CRS)
    p10["geom_area"], p20["geom_area"] = p10.geometry.area, p20.geometry.area
    p10 = p10[["GEOID", "ALAND", "geom_area", "geometry"]].rename(columns={"GEOID": "g10", "ALAND": "aland10", "geom_area": "area10"})
    p20 = p20[["GEOID", "ALAND", "geom_area", "geometry"]].rename(columns={"GEOID": "g20", "ALAND": "aland20", "geom_area": "area20"})
    ov = gpd.overlay(p10, p20, how="intersection", keep_geom_type=True)
    ov["a_ov"] = ov.geometry.area
    ov = ov[ov["a_ov"] > 0].copy()
    ov["s10"] = ov["a_ov"] / ov["area10"]
    ov["s20"] = ov["a_ov"] / ov["area20"]
    ov["s10"] = ov["s10"].clip(upper=1.0)
    ov["s20"] = ov["s20"].clip(upper=1.0)

    def stable_set(df, thresh):
        sig = df[(df["s10"] > SIG) & (df["s20"] > SIG)]
        n10 = sig.groupby("g10").size()
        n20 = sig.groupby("g20").size()
        m = df[(df["s10"] >= thresh) & (df["s20"] >= thresh)]
        m = m[m["g10"].map(n10).eq(1) & m["g20"].map(n20).eq(1)]
        return set(zip(m["g10"], m["g20"]))

    sql_set = set(con.execute("SELECT geoid_2010, geoid_2020 FROM v_stable_tract").fetchall())
    say("## (b) Stable tract cross-check (2010 vs 2020 tracts)")
    say()
    say(f"Overlay in {AREA_CRS} on total polygon area (land plus water, because TIGER polygons carry no separate land geometry). "
        f"Rule is the same as v_stable_tract: overlap at least {THRESH:.0%} of both tracts and one-to-one among pieces larger than {SIG:.0%}.")
    say()
    say(f"Overlay pieces with positive area: {len(ov)}.")
    say()
    say(f"v_stable_tract (Census land-area relationship file): {len(sql_set)} tracts.")
    say()
    say("| Threshold on geometry area | Stable pairs (overlay) | In both | Only overlay | Only SQL view | Jaccard agreement |")
    say("|---|---|---|---|---|---|")
    results = {}
    for th in (0.99, 0.98, 0.95):
        s = stable_set(ov, th)
        results[th] = s
        both = len(s & sql_set)
        say(f"| {th:.2f} | {len(s)} | {both} | {len(s - sql_set)} | {len(sql_set - s)} | {both / len(s | sql_set):.3f} |")
    say()
    s99 = results[0.99]
    # reconcile land area share used by SQL with geometry share for the differing pairs
    diff = sorted((s99 ^ sql_set))
    if diff:
        xw = con.execute("SELECT * FROM xwalk_tract_2010_2020").df().set_index(["geoid_2010", "geoid_2020"])
        say("Pairs that differ at the 0.99 threshold (first 25):")
        say()
        say("| geoid_2010 | geoid_2020 | In overlay set | In SQL set | Geometry share of 2010 | Geometry share of 2020 | Land share of 2010 | Land share of 2020 |")
        say("|---|---|---|---|---|---|---|---|")
        ovi = ov.set_index(["g10", "g20"])
        for k in diff[:25]:
            gs = ovi.loc[k] if k in ovi.index else None
            gs10 = f"{gs['s10']:.4f}" if gs is not None else "n/a"
            gs20 = f"{gs['s20']:.4f}" if gs is not None else "n/a"
            if k in xw.index and xw.loc[k]["aland_2010"] > 0 and xw.loc[k]["aland_2020"] > 0:
                r = xw.loc[k]
                l10, l20 = f"{r['aland_overlap'] / r['aland_2010']:.4f}", f"{r['aland_overlap'] / r['aland_2020']:.4f}"
            else:
                l10 = l20 = "n/a (no land)"
            say(f"| {k[0]} | {k[1]} | {k in s99} | {k in sql_set} | {gs10} | {gs20} | {l10} | {l20} |")
        say()
    n_agree_pct = 100 * len(s99 & sql_set) / len(s99 | sql_set)
    say(f"Result: at the 0.99 threshold the overlay finds {len(s99)} stable pairs against {len(sql_set)} in the SQL view; "
        f"{len(s99 & sql_set)} are in both ({n_agree_pct:.1f} percent of the union).")
    say()

    # (c) centroid in polygon
    say("## (c) Internal point inside own tract polygon")
    say()
    say("TIGER INTPTLAT and INTPTLON (the Census internal point) are joined to the polygons with a spatial join (predicate within).")
    say()
    say("| Layer | Tracts | Internal points inside own tract | Not inside own tract | Inside a different tract | Inside no tract |")
    say("|---|---|---|---|---|---|")
    for label, g in (("2010 tracts", g10), ("2020 tracts", g20)):
        pts = gpd.GeoDataFrame(
            g[["GEOID"]].copy(),
            geometry=gpd.points_from_xy(g["INTPTLON"].astype(float), g["INTPTLAT"].astype(float)), crs=g.crs)
        j = gpd.sjoin(pts, g[["GEOID", "geometry"]].rename(columns={"GEOID": "GEOID_poly"}), how="left", predicate="within")
        own = j[j["GEOID"] == j["GEOID_poly"]]["GEOID"].nunique()
        other = j[j["GEOID_poly"].notna() & (j["GEOID"] != j["GEOID_poly"])]["GEOID"].nunique()
        none = j[j["GEOID_poly"].isna()]["GEOID"].nunique()
        say(f"| {label} | {len(g)} | {own} | {len(g) - own} | {other} | {none} |")
        bad = j[j["GEOID"] != j["GEOID_poly"]]["GEOID"].tolist()
        if bad:
            print(f"  {label} tracts whose internal point is not inside them: {bad}")
    say()
    say("Internal points are chosen by the Census Bureau and are not guaranteed to be inside irregular tracts, so misses are possible on lakefront or non-convex tracts.")
    con.close()
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "spatial_checks.md").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
