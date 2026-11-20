"""Static choropleth maps for the neighborhood indicators, saved to docs/img/.
Values come from DuckDB and are joined to TIGER polygons by GEOID.

Run: python -I src/06_maps.py
"""
from pathlib import Path
import duckdb
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TIGER = ROOT / "data_raw" / "tiger"
DB = ROOT / "data" / "cuyahoga.duckdb"
IMG = ROOT / "docs" / "img"
DPI = 110
WATER_TRACT = "39035990000"  # water-only tract, never drawn
GREY = "#e3e3e3"
EDGE = "#8a8a8a"
SRC = "Source: U.S. Census Bureau ACS 5-year estimates and TIGER/Line tracts; calculations in this project."
LAKE_NOTE = "Tract polygons include Lake Erie waters."
sizes = []


def load_tracts(zipname):
    g = gpd.read_file(f"zip://{TIGER / zipname}")
    g = g[g["COUNTYFP"] == "035"][["GEOID", "geometry"]].to_crs("EPSG:5070")
    return g[g["GEOID"] != WATER_TRACT].reset_index(drop=True)


def indicator(con, ind, vintage, col="value"):
    q = f"SELECT geoid, {col} AS v FROM v_indicator_adj WHERE geo_level='tract' AND vintage=? AND indicator_id=?"
    return con.execute(q, [vintage, ind]).df().set_index("geoid")["v"]


def draw(ax, gdf, col, cmap, norm, label_na=True):
    have = gdf[gdf[col].notna()]
    na = gdf[gdf[col].isna()]
    if len(na):
        na.plot(ax=ax, facecolor=GREY, edgecolor=EDGE, hatch="////", linewidth=0.2)
    have.plot(ax=ax, column=col, cmap=cmap, norm=norm, edgecolor="white", linewidth=0.15)
    ax.set_axis_off()
    return len(na)


def colorbar(fig, ax, cmap, norm, label, extend="both", fmt=None):
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01, extend=extend)
    cb.set_label(label)
    if fmt:
        cb.ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt))
    return cb


def finish(fig, name, note):
    fig.text(0.01, 0.01, note, fontsize=7, color="#444444", ha="left", va="bottom", wrap=True)
    path = IMG / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    kb = path.stat().st_size / 1024
    sizes.append((name, kb))
    print(f"  wrote {path.relative_to(ROOT)} ({kb:.0f} KB)")


def clip_range(s, lo=2, hi=98):
    return float(np.nanpercentile(s, lo)), float(np.nanpercentile(s, hi))


def single_map(gdf, values, name, title, cmap, label, fmt=None, extra=""):
    g = gdf.copy()
    g["val"] = g["GEOID"].map(values)
    missing = g[g["val"].isna()]["GEOID"].tolist()
    print(f"{name}: {len(missing)} tracts with no value: {missing}")
    vmin, vmax = clip_range(g["val"])
    norm = Normalize(vmin=vmin, vmax=vmax)
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    draw(ax, g, "val", cmap, norm)
    ax.set_title(title, fontsize=12)
    colorbar(fig, ax, cmap, norm, label, fmt=fmt)
    ax.legend(handles=[Patch(facecolor=GREY, edgecolor=EDGE, hatch="////", label=f"No value ({len(missing)} tracts)")],
              loc="lower left", fontsize=8, frameon=False)
    note = (f"{SRC}\nColour range is the 2nd to 98th percentile of tract values (values beyond are clipped). "
            f"Hatched grey tracts have no usable estimate (suppressed, zero denominator or missing). {LAKE_NOTE}{extra}")
    finish(fig, name, note)
    return missing


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    t20, t10 = load_tracts("tl_2024_39_tract.zip"), load_tracts("tl_2017_39_tract.zip")
    pct = lambda x, _: f"{x:.0f}%"
    usd = lambda x, _: f"${x / 1000:.0f}k"

    pov = indicator(con, "poverty_rate", "2020-2024")
    single_map(t20, pov, "map_poverty_2020_2024.png", "Poverty rate, 2020-2024 (ACS 5-year)",
               "YlOrRd", "Persons below poverty (percent)", pct)

    inc24 = indicator(con, "median_hh_income", "2020-2024", "value_2024usd")
    inc17 = indicator(con, "median_hh_income", "2013-2017", "value_2024usd")
    both = pd.concat([inc17, inc24])
    vmin, vmax = clip_range(both)
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = "viridis"
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6))
    for ax, gdf, vals, ttl in ((axes[0], t10, inc17, "2013-2017 (2010 tracts)"), (axes[1], t20, inc24, "2020-2024 (2020 tracts)")):
        g = gdf.copy()
        g["val"] = g["GEOID"].map(vals)
        miss = g[g["val"].isna()]["GEOID"].tolist()
        print(f"map_income_2013_2017_vs_2020_2024.png panel {ttl}: {len(miss)} tracts with no value: {miss}")
        draw(ax, g, "val", cmap, norm)
        ax.set_title(f"{ttl}, {len(miss)} hatched", fontsize=10)
    fig.suptitle("Median household income in 2024 dollars", fontsize=12)
    colorbar(fig, axes, cmap, norm, "2024 dollars", fmt=usd)
    finish(fig, "map_income_2013_2017_vs_2020_2024.png",
           f"{SRC}\n2013-2017 dollars are inflated to 2024 with CPI-U. Common colour range is the 2nd to 98th percentile of all values shown. "
           f"The two panels use different tract boundaries (2010 and 2020). Hatched grey tracts have no usable estimate. {LAKE_NOTE}")

    inc_single = indicator(con, "median_hh_income", "2020-2024", "value")
    single_map(t20, inc_single, "map_income_2020_2024.png", "Median household income, 2020-2024 (2024 dollars)",
               "viridis", "Dollars", usd)

    single_map(t20, indicator(con, "rent_burden_30", "2020-2024"), "map_rent_burden_2020_2024.png",
               "Rent burden, 30 percent or more of income, 2020-2024", "PuBu", "Renter households (percent)", pct)
    single_map(t20, indicator(con, "other_vacant", "2020-2024"), "map_other_vacant_2020_2024.png",
               "Other vacant units, share of housing units, 2020-2024", "Purples", "Housing units (percent)", pct)

    # change in poverty rate on stable tracts
    ch = con.execute("""SELECT geoid_2020 AS geoid, change, change_moe, distinguishable FROM v_change_stable
                        WHERE indicator_id = 'poverty_rate'""").df().set_index("geoid")
    g = t20.copy()
    g = g.merge(ch, left_on="GEOID", right_index=True, how="left")
    n_stable = int(con.execute("SELECT count(*) FROM v_stable_tract").fetchone()[0])
    has = g["change"].notna()
    sig = has & (g["distinguishable"] == True)
    nosig = has & ~sig
    print(f"Poverty change map: stable tracts {n_stable}; with change value {int(has.sum())}; distinguishable {int(sig.sum())}; "
          f"not distinguishable (hatched) {int(nosig.sum())}")
    stable_ids = set(con.execute("SELECT geoid_2020 FROM v_stable_tract").df()["geoid_2020"])
    nov = g[g["GEOID"].isin(stable_ids) & ~has]["GEOID"].tolist()
    print(f"  stable tracts with no change value: {len(nov)}: {nov}")
    notstable = int((~g["GEOID"].isin(stable_ids)).sum())
    print(f"  tracts not in the stable set (light grey): {notstable}")
    lim = float(np.nanpercentile(np.abs(g["change"]), 98))
    norm = TwoSlopeNorm(vcenter=0, vmin=-lim, vmax=lim)
    cmap = "RdBu_r"
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    g[~has].plot(ax=ax, facecolor=GREY, edgecolor="white", linewidth=0.15)
    g[has].plot(ax=ax, column="change", cmap=cmap, norm=norm, edgecolor="white", linewidth=0.15)
    g[nosig].plot(ax=ax, facecolor="none", edgecolor="#333333", hatch="////", linewidth=0.0)
    ax.set_axis_off()
    ax.set_title("Change in poverty rate, 2013-2017 to 2020-2024, stable tracts", fontsize=12)
    colorbar(fig, ax, cmap, norm, "Change (percentage points)", fmt=lambda x, _: f"{x:+.0f}")
    ax.legend(handles=[Patch(facecolor="white", edgecolor="#333333", hatch="////",
                             label=f"Change not distinguishable from zero at 90% ({int(nosig.sum())})"),
                       Patch(facecolor=GREY, edgecolor="white", label=f"Not a stable tract or no value ({int((~has).sum())})")],
              loc="lower left", fontsize=8, frameon=False)
    finish(fig, "map_poverty_change_stable.png",
           f"{SRC}\nOnly tracts with essentially unchanged boundaries (v_stable_tract: {n_stable} tracts) are compared. "
           f"A change is distinguishable when its absolute value exceeds the margin of error of the difference. "
           f"Colour range is the 98th percentile of absolute change. {LAKE_NOTE}")

    # geocoded points over poverty
    pts = con.execute("SELECT lon, lat, match_status FROM geocode_sample WHERE lon IS NOT NULL AND lat IS NOT NULL").df()
    total = int(con.execute("SELECT count(*) FROM geocode_sample").fetchone()[0])
    gp = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4269").to_crs("EPSG:5070")
    g = t20.copy()
    g["val"] = g["GEOID"].map(pov)
    norm = Normalize(*clip_range(g["val"]))
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    draw(ax, g, "val", "YlOrRd", norm)
    gp.plot(ax=ax, color="#1f2d5c", markersize=9, edgecolor="white", linewidth=0.4)
    ax.set_title("Geocoded public schools over poverty rate, 2020-2024", fontsize=12)
    colorbar(fig, ax, "YlOrRd", norm, "Persons below poverty (percent)", fmt=pct)
    ax.legend(handles=[plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="#1f2d5c", markeredgecolor="white",
                                  label=f"Geocoded school ({len(gp)} of {total} sampled)"),
                       Patch(facecolor=GREY, edgecolor=EDGE, hatch="////", label="No poverty value")],
              loc="lower left", fontsize=8, frameon=False)
    finish(fig, "map_geocoded_points_poverty.png",
           f"{SRC}\nPoints: NCES Common Core of Data school addresses geocoded with the U.S. Census Geocoder (src/05_geocode.py). "
           f"Unmatched addresses are not shown. {LAKE_NOTE}")
    print("Largest image size KB:", f"{max(s for _, s in sizes):.0f}")
    con.close()


if __name__ == "__main__":
    main()
