"""Build data/cuyahoga.duckdb from the extracted ACS rows, TIGER attributes and the
2010-2020 tract relationship file. Applies sql/01..03.

Run: python -I src/02_build_db.py
"""
import csv
from pathlib import Path
import duckdb
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
DB = ROOT / "data" / "cuyahoga.duckdb"
COUNTY = "035"


def run_sql(con, name):
    con.execute((ROOT / "sql" / name).read_text(encoding="utf-8"))


def tract_attrs(zipname, tract_vintage):
    g = gpd.read_file(f"zip://{RAW / 'tiger' / zipname}")
    g = g[g["COUNTYFP"] == COUNTY]
    return pd.DataFrame({
        "tract_vintage": tract_vintage, "geoid": g["GEOID"], "county_fips": "39" + COUNTY,
        "tract_code": g["TRACTCE"], "name": g["NAMELSAD"], "aland_m2": g["ALAND"].astype("int64"),
        "awater_m2": g["AWATER"].astype("int64"),
        "intpt_lat": g["INTPTLAT"].astype(float), "intpt_lon": g["INTPTLON"].astype(float)})


def main():
    DB.parent.mkdir(exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    run_sql(con, "01_schema.sql")

    cpi = pd.read_csv(ROOT / "data" / "cpi_u_annual.csv").set_index("year")["cpi_u_annual_avg"]
    vint = pd.DataFrame([
        ("2013-2017", 2017, 2010, 2017, float(cpi[2017])),
        ("2020-2024", 2024, 2020, 2024, float(cpi[2024]))],
        columns=["vintage", "end_year", "tract_vintage", "dollar_year", "cpi_u"])
    con.execute("INSERT INTO dim_vintage SELECT * FROM vint")

    tr = pd.concat([tract_attrs("tl_2017_39_tract.zip", 2010), tract_attrs("tl_2024_39_tract.zip", 2020)])
    con.execute("INSERT INTO dim_tract SELECT * FROM tr")

    # variables: from the 2024 table shells (labels are the same across these vintages)
    rows = []
    with open(RAW / "acs2024" / "ACS20245YR_Table_Shells.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="|"):
            if r[0] in ("B01002", "B01003", "B11003", "B15003", "B17001", "B19013", "B23025", "B25002",
                        "B25003", "B25004", "B25044", "B25070", "B25077") and r[3].startswith("B"):
                rows.append((r[3], r[0], int(float(r[1])), r[4], r[5], r[6]))
    dv = pd.DataFrame(rows, columns=["variable", "table_id", "line", "label", "table_title", "universe"]) \
        .drop_duplicates("variable")
    con.execute("INSERT INTO dim_variable SELECT * FROM dv")

    fact = pd.read_parquet(ROOT / "data" / "interim" / "acs_long.parquet")
    con.execute("INSERT INTO fact_acs SELECT vintage, geo_level, geoid, variable, estimate, moe, nullif(flag, '') FROM fact")

    x = pd.read_csv(RAW / "xwalk" / "tab20_tract20_tract10_natl.txt", sep="|", dtype=str, encoding="utf-8-sig")
    x = x[x["GEOID_TRACT_20"].str.startswith("39" + COUNTY) & x["GEOID_TRACT_10"].str.startswith("39" + COUNTY)]
    xw = pd.DataFrame({"geoid_2010": x["GEOID_TRACT_10"], "geoid_2020": x["GEOID_TRACT_20"],
                       "aland_2010": x["AREALAND_TRACT_10"].astype("int64"),
                       "aland_2020": x["AREALAND_TRACT_20"].astype("int64"),
                       "aland_overlap": x["AREALAND_PART"].astype("int64")})
    con.execute("INSERT INTO xwalk_tract_2010_2020 SELECT * FROM xw")

    run_sql(con, "02_indicator_defs.sql")
    run_sql(con, "03_views.sql")
    for t in ("dim_vintage", "dim_tract", "dim_variable", "fact_acs", "xwalk_tract_2010_2020", "indicator_def", "indicator_cell"):
        print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    print("v_indicator rows", con.execute("SELECT count(*) FROM v_indicator").fetchone()[0])
    print("stable tracts", con.execute("SELECT count(*) FROM v_stable_tract").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
