"""Extract Cuyahoga County (FIPS 39035) tract and county rows for 13 ACS tables
from two vintages into one long table: data/interim/acs_long.parquet.

Vintage 2013-2017: classic summary file (sequence files, 2010 census tracts).
Vintage 2020-2024: table-based summary file (one pipe-delimited file per table,
2020 census tracts).

Columns: vintage, geo_level (tract|county), geoid, variable, estimate, moe, flag.
Sentinel codes of the Census Bureau (negative nine-digit numbers) are turned into
NULL and recorded in `flag`, never silently dropped or treated as numbers.
"""
import csv, io, re, zipfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
OUT = ROOT / "data" / "interim"
TABLES = ["B01002", "B01003", "B11003", "B15003", "B17001", "B19013", "B23025",
          "B25002", "B25003", "B25004", "B25044", "B25070", "B25077"]
COUNTY = "39035"
SENTINELS = {-666666666: "no_estimate", -555555555: "median_in_open_interval",
             -333333333: "median_in_open_interval_upper", -222222222: "too_few_sample_cases",
             -999999999: "not_available", -888888888: "not_applicable"}


def clean(v):
    """Return (value or None, flag or '')."""
    if v is None or v == "":
        return None, "blank"
    try:
        x = float(v)
    except ValueError:
        return None, "non_numeric"
    if x in SENTINELS:
        return None, SENTINELS[int(x)]
    if x <= -100000000:
        return None, "unknown_sentinel"
    return x, ""


def vintage_2024():
    frames = []
    for t in TABLES:
        path = RAW / "acs2024" / f"acsdt5y2024-{t.lower()}.dat"
        with open(path, encoding="utf-8") as f:
            header = f.readline().rstrip("\n").split("|")
            for line in f:
                if not (line.startswith("1400000US" + COUNTY) or line.startswith("0500000US" + COUNTY)):
                    continue
                parts = line.rstrip("\n").split("|")
                geo = parts[0]
                level = "tract" if geo.startswith("140") else "county"
                geoid = geo.split("US")[1]
                for name, val in zip(header[1:], parts[1:]):
                    var = name[:-2] + ""  # e.g. B17001_E002 -> B17001_
                    kind = name.split("_")[1][0]  # E or M
                    num = name.split("_")[1][1:]
                    frames.append((geoid, level, f"{t}_{num}", kind, val))
    df = pd.DataFrame(frames, columns=["geoid", "geo_level", "variable", "kind", "raw"])
    return df


def lookup_2017():
    """table -> (sequence, start position 1-based, number of cells)."""
    res = {}
    with open(RAW / "acs2017" / "ACS_5yr_Seq_Table_Number_Lookup.txt", encoding="latin-1", newline="") as f:
        for r in csv.reader(f):
            if len(r) > 6 and r[1] in TABLES and r[4].strip():
                res[r[1]] = (r[2], int(r[4]), int(re.match(r"(\d+)", r[5]).group(1)))
    return res


def geo_2017(zf):
    name = "g20175oh.csv"
    out = {}
    for r in csv.reader(io.TextIOWrapper(zf.open(name), encoding="latin-1")):
        gid = next((x for x in r if re.match(r"^(140|050)00US39", x)), None)
        if gid and gid.split("US")[1].startswith(COUNTY):
            out[r[4]] = ("tract" if gid.startswith("140") else "county", gid.split("US")[1])
    return out


def vintage_2017():
    lk = lookup_2017()
    assert set(lk) == set(TABLES), set(TABLES) - set(lk)
    rows = []
    for zname, want in (("Ohio_Tracts_Block_Groups_Only.zip", "tract"),
                        ("Ohio_All_Geographies_Not_Tracts_Block_Groups.zip", "county")):
        zf = zipfile.ZipFile(RAW / "acs2017" / zname)
        geo = {k: v for k, v in geo_2017(zf).items() if v[0] == want}
        for t, (seq, start, ncell) in lk.items():
            for kind, pre in (("E", "e"), ("M", "m")):
                member = f"{pre}20175oh{seq}000.txt"
                with zf.open(member) as fh:
                    for r in csv.reader(io.TextIOWrapper(fh, encoding="latin-1")):
                        g = geo.get(r[5])
                        if not g:
                            continue
                        for i in range(ncell):
                            val = r[start - 1 + i] if start - 1 + i < len(r) else ""
                            rows.append((g[1], g[0], f"{t}_{i + 1:03d}", kind, val))
    return pd.DataFrame(rows, columns=["geoid", "geo_level", "variable", "kind", "raw"])


def finish(df, vintage):
    vals = df["raw"].map(clean)
    df["value"] = [v[0] for v in vals]
    df["flag"] = [v[1] for v in vals]
    est = df[df.kind == "E"].rename(columns={"value": "estimate", "flag": "flag_e"})
    moe = df[df.kind == "M"].rename(columns={"value": "moe", "flag": "flag_m"})
    m = est[["geoid", "geo_level", "variable", "estimate", "flag_e"]].merge(
        moe[["geoid", "variable", "moe", "flag_m"]], on=["geoid", "variable"], how="outer")
    m["flag"] = (m["flag_e"].fillna("") + "|" + m["flag_m"].fillna("")).str.strip("|")
    m["vintage"] = vintage
    return m[["vintage", "geo_level", "geoid", "variable", "estimate", "moe", "flag"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = finish(vintage_2017(), "2013-2017")
    b = finish(vintage_2024(), "2020-2024")
    df = pd.concat([a, b], ignore_index=True)
    df.to_parquet(OUT / "acs_long.parquet", index=False)
    summ = df.groupby(["vintage", "geo_level"]).agg(geoids=("geoid", "nunique"), rows=("variable", "size"),
                                                    null_est=("estimate", lambda s: s.isna().sum()))
    print(summ)


if __name__ == "__main__":
    main()
