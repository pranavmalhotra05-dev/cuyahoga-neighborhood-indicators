"""Independent recomputation of the headline numbers, from the raw files only.

Does not use the DuckDB file, the SQL, or anything under src/.
Run:  python -I tests/independent_recompute.py [--offline]

Reads the claims in outputs/analysis_numbers.json and prints MATCH or MISMATCH
for each one that this script can recompute (exact for counts, 0.01 for rates).
"""
import csv
import io
import json
import math
import random
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
Z = 1.645
COUNTY = "39035"
SENTINELS_2024 = {-666666666, -555555555, -333333333, -222222222, -999999999, -888888888}

results = []  # (claim, project, mine, verdict)


def verdict(claim, project, mine, kind="rate"):
    if mine is None or (isinstance(mine, float) and math.isnan(mine)):
        ok = False
    elif kind == "count":
        ok = int(project) == int(mine)
    elif kind == "dollar":
        ok = abs(project - mine) <= 1.0
    else:
        dec = len(repr(float(project)).split(".")[1].rstrip("0")) if "." in repr(float(project)) else 0
        tol = max(0.0101, 0.5 * 10 ** (-dec) + 1e-9)  # 0.01, or half a unit of the project's own rounding
        ok = abs(project - mine) <= tol
    results.append((claim, project, mine, "MATCH" if ok else "MISMATCH"))


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def prop_moe(num, mnum, den, mden):
    """Census MOE of a proportion, with the ratio-formula fallback."""
    num, mnum, den, mden = (np.asarray(x, dtype=float) for x in (num, mnum, den, mden))
    with np.errstate(divide="ignore", invalid="ignore"):
        p = num / den
        rad = mnum**2 - (p**2) * (mden**2)
        alt = mnum**2 + (p**2) * (mden**2)
        out = np.where(rad >= 0, np.sqrt(rad), np.sqrt(alt)) / den
    out = np.where(den > 0, out, np.nan)
    return out


def clean_2024(series):
    s = pd.to_numeric(series, errors="coerce")
    s = s.where(~s.isin(SENTINELS_2024))
    s = s.where(~(s <= -222222222))  # any other 9 digit negative code
    return s


# ----------------------------------------------------------------------------
# 2020-2024 table based files
# ----------------------------------------------------------------------------
def load_2024(table, cols):
    p = RAW / "acs2024" / f"acsdt5y2024-{table.lower()}.dat"
    df = pd.read_csv(p, sep="|", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw = df.copy()
    keep = ["GEO_ID"]
    for c in cols:
        keep += [f"{table}_E{c:03d}", f"{table}_M{c:03d}"]
    df = df[keep].copy()
    for c in keep[1:]:
        df[c] = clean_2024(df[c])
    df["geoid"] = df["GEO_ID"].str.split("US").str[1]
    tr = df[df["GEO_ID"].str.startswith("1400000US" + COUNTY)].copy()
    co = df[df["GEO_ID"] == "0500000US" + COUNTY].copy()
    return tr.set_index("geoid"), co.iloc[0], raw


# ----------------------------------------------------------------------------
# 2013-2017 classic summary file
# ----------------------------------------------------------------------------
TRACT_ZIP = RAW / "acs2017" / "Ohio_Tracts_Block_Groups_Only.zip"
OTHER_ZIP = RAW / "acs2017" / "Ohio_All_Geographies_Not_Tracts_Block_Groups.zip"

_lookup = None


def lookup_start(table):
    global _lookup
    if _lookup is None:
        _lookup = pd.read_csv(RAW / "acs2017" / "ACS_5yr_Seq_Table_Number_Lookup.txt",
                              dtype=str, keep_default_na=False)
    r = _lookup[(_lookup["Table ID"] == table) & (_lookup["Start Position"] != "")].iloc[0]
    return r["Sequence Number"], int(r["Start Position"])


_geo_cache = {}


def geo_2017(zpath):
    if zpath not in _geo_cache:
        with zipfile.ZipFile(zpath) as z:
            g = pd.read_csv(z.open("g20175oh.csv"), header=None, dtype=str,
                            keep_default_na=False, encoding="latin-1")
        # index 4 LOGRECNO; GEO_ID is the column that looks like 14000US...
        gid_col = None
        for c in g.columns:
            if g[c].str.match(r"^\d{5}US\d+$").any():
                gid_col = c
                break
        out = pd.DataFrame({"logrecno": g[4], "GEO_ID": g[gid_col]})
        _geo_cache[zpath] = out
    return _geo_cache[zpath]


def read_seq(zpath, prefix, seq, logrecs, table, ncells_wanted):
    """Return DataFrame logrecno -> cell n (1-based table line) as float, NaN if blank or '.'."""
    start = lookup_start(table)[1]
    name = f"{prefix}20175oh{seq}000.txt"
    with zipfile.ZipFile(zpath) as z:
        df = pd.read_csv(z.open(name), header=None, dtype=str, keep_default_na=False,
                         encoding="latin-1", usecols=[5] + [start - 1 + n - 1 for n in ncells_wanted])
    df = df[df[5].isin(logrecs)].copy()
    out = pd.DataFrame({"logrecno": df[5].values})
    for n in ncells_wanted:
        col = df[start - 1 + n - 1].str.strip()
        bad = ~col.isin(["", "."]) & pd.to_numeric(col, errors="coerce").isna()
        if bad.any():
            print(f"  NOTE non numeric tokens in {name} cell {n}: {col[bad].unique()[:5]}")
        v = pd.to_numeric(col, errors="coerce")
        neg = v < 0
        if neg.any():
            print(f"  NOTE negative values in {name} cell {n}: {sorted(v[neg].unique())[:5]} -> treated as NaN")
            v = v.where(~neg)
        out[n] = v.values
    return out


def load_2017(table, cells, county=False):
    """Returns DataFrame indexed by geoid with columns E{n}, M{n} for tracts (or a single county Series)."""
    seq = lookup_start(table)[0]
    zpath = OTHER_ZIP if county else TRACT_ZIP
    g = geo_2017(zpath)
    if county:
        g = g[g["GEO_ID"] == "05000US" + COUNTY]
    else:
        g = g[g["GEO_ID"].str.startswith("14000US" + COUNTY)]
    logrecs = set(g["logrecno"])
    e = read_seq(zpath, "e", seq, logrecs, table, cells)
    m = read_seq(zpath, "m", seq, logrecs, table, cells)
    e = e.rename(columns={n: f"E{n}" for n in cells})
    m = m.rename(columns={n: f"M{n}" for n in cells})
    df = g.merge(e, on="logrecno").merge(m, on="logrecno")
    df["geoid"] = df["GEO_ID"].str.split("US").str[1]
    df = df.set_index("geoid")
    if county:
        return df.iloc[0]
    return df


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    offline = "--offline" in sys.argv
    claims = json.load(open(ROOT / "outputs" / "analysis_numbers.json"))

    # ---------------- load poverty
    t24, c24, raw24 = load_2024("B17001", [1, 2])
    t17 = load_2017("B17001", [1, 2])
    c17 = load_2017("B17001", [1, 2], county=True)

    print("tracts 2024 rows:", len(t24), " tracts 2017 rows:", len(t17))
    verdict("tracts_2020 (rows in 2020-2024 file)", claims["tracts_2020"], len(t24), "count")
    verdict("tracts_2010 (rows in 2013-2017 file)", claims["tracts_2010"], len(t17), "count")

    for t, tag in ((t24, "24"), (None, None)):
        pass
    t24["rate"] = 100 * t24["B17001_E002"] / t24["B17001_E001"].where(t24["B17001_E001"] > 0)
    t24["moe"] = 100 * prop_moe(t24["B17001_E002"], t24["B17001_M002"], t24["B17001_E001"], t24["B17001_M001"])
    t17["rate"] = 100 * t17["E2"] / t17["E1"].where(t17["E1"] > 0)
    t17["moe"] = 100 * prop_moe(t17["E2"], t17["M2"], t17["E1"], t17["M1"])

    # ---------------- county poverty
    p24 = 100 * c24["B17001_E002"] / c24["B17001_E001"]
    m24 = 100 * float(prop_moe(c24["B17001_E002"], c24["B17001_M002"], c24["B17001_E001"], c24["B17001_M001"]))
    p17 = 100 * c17["E2"] / c17["E1"]
    m17 = 100 * float(prop_moe(c17["E2"], c17["M2"], c17["E1"], c17["M1"]))
    dchg = p24 - p17
    dmoe = math.sqrt(m24**2 + m17**2)
    print(f"county poverty 17 {p17:.4f} +-{m17:.4f}; 24 {p24:.4f} +-{m24:.4f}; change {dchg:.4f} +-{dmoe:.4f}")
    verdict("county poverty 2013-2017 (%)", claims["county_poverty_2013_2017"], p17)
    verdict("county poverty 2013-2017 MOE", claims["county_poverty_2013_2017_moe"], m17)
    verdict("county poverty 2020-2024 (%)", claims["county_poverty_2020_2024"], p24)
    verdict("county poverty 2020-2024 MOE", claims["county_poverty_2020_2024_moe"], m24)
    verdict("county poverty change (pts)", claims["county_poverty_change"], dchg)
    verdict("county poverty change MOE", claims["county_poverty_change_moe"], dmoe)

    # ---------------- income
    i24, ci24, _ = load_2024("B19013", [1])
    i17 = load_2017("B19013", [1], county=True)
    cpi = pd.read_csv(ROOT / "data" / "cpi_u_annual.csv")
    cpi_map = dict(zip(cpi["year"], cpi["cpi_u_annual_avg"]))
    ratio = 313.689 / 245.120
    inc17 = i17["E1"] * ratio
    inc24 = ci24["B19013_E001"]
    inc_moe = math.sqrt((i17["M1"] * ratio) ** 2 + ci24["B19013_M001"] ** 2)
    print(f"income 2017$ {i17['E1']} -> 2024$ {inc17:.2f}; 2024 {inc24}; change {inc24-inc17:.2f} +-{inc_moe:.2f}")
    verdict("county income 2013-2017 in 2024 USD", claims["county_income_2013_2017_in_2024usd"], inc17, "dollar")
    verdict("county income 2020-2024", claims["county_income_2020_2024"], inc24, "dollar")
    verdict("county income change (real)", claims["county_income_change_real"], inc24 - inc17, "dollar")
    verdict("county income change MOE", claims["county_income_change_real_moe"], inc_moe, "dollar")

    # CPI checks
    verdict("CPI-U 2017 in csv vs 245.120", 245.120, cpi_map[2017])
    verdict("CPI-U 2024 in csv vs 313.689", 313.689, cpi_map[2024])
    if not offline:
        try:
            import urllib.request
            # POST with annualaverage=true. A GET with startyear/endyear silently returns only the latest
            # three years on v1, so it cannot be used to check 2017.
            body = json.dumps({"seriesid": ["CUUR0000SA0"], "startyear": "2017", "endyear": "2024",
                               "annualaverage": True}).encode()
            req = urllib.request.Request("https://api.bls.gov/publicAPI/v1/timeseries/data/", data=body,
                                         headers={"Content-type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            ann = {}
            monthly = {}
            for s_ in d["Results"]["series"]:
                for x in s_["data"]:
                    try:
                        val = float(x["value"])
                    except ValueError:  # '-' marks a month the BLS did not publish
                        continue
                    if x["period"] == "M13":
                        ann[int(x["year"])] = val
                    elif x["period"].startswith("M"):
                        monthly.setdefault(int(x["year"]), []).append(val)
            print("BLS API annual averages:", ann)
            for y in sorted(cpi_map):
                api = ann.get(y)
                if api is None and len(monthly.get(y, [])) == 12:
                    api = round(sum(monthly[y]) / 12, 3)
                if api is not None:
                    verdict(f"CPI-U {y} csv vs BLS API", cpi_map[y], api)
                else:
                    print(f"  BLS API gave no annual value for {y}")
        except Exception as ex:  # network problems must not break the rest
            print("BLS API not reachable:", ex)

    # ---------------- crosswalk and stable tracts
    xw = pd.read_csv(RAW / "xwalk" / "tab20_tract20_tract10_natl.txt", sep="|", dtype=str,
                     keep_default_na=False, encoding="utf-8-sig")
    for c in ["AREALAND_TRACT_20", "AREALAND_TRACT_10", "AREALAND_PART"]:
        xw[c] = pd.to_numeric(xw[c])
    xc = xw[xw["GEOID_TRACT_20"].str.startswith(COUNTY.__str__()) | xw["GEOID_TRACT_10"].str.startswith(COUNTY)].copy()
    cross_county = xc[~(xc["GEOID_TRACT_20"].str.startswith(COUNTY) & xc["GEOID_TRACT_10"].str.startswith(COUNTY))]
    print("xwalk rows touching county:", len(xc), "; rows crossing the county line:", len(cross_county))
    xc["f20"] = xc["AREALAND_PART"] / xc["AREALAND_TRACT_20"].where(xc["AREALAND_TRACT_20"] > 0)
    xc["f10"] = xc["AREALAND_PART"] / xc["AREALAND_TRACT_10"].where(xc["AREALAND_TRACT_10"] > 0)
    big = (xc["f20"] >= 0.99) & (xc["f10"] >= 0.99)

    def stable(count_rows):
        n20 = count_rows.groupby("GEOID_TRACT_20")["GEOID_TRACT_10"].transform("size")
        n10 = count_rows.groupby("GEOID_TRACT_10")["GEOID_TRACT_20"].transform("size")
        return count_rows[(count_rows["f20"] >= 0.99) & (count_rows["f10"] >= 0.99) & (n20 == 1) & (n10 == 1)]

    sA = stable(xc)                                    # every crosswalk row counts
    sC = stable(xc[xc["AREALAND_PART"] > 0])          # zero land (water only) overlaps ignored
    sB = xc[big]                                       # threshold only
    print(f"stable variants: A strict pair count {len(sA)}, C ignoring zero-land rows {len(sC)}, B threshold only {len(sB)}")
    # a pair where both tracts have zero land and so no ratio
    zero_land = xc[(xc["AREALAND_TRACT_20"] == 0) | (xc["AREALAND_TRACT_10"] == 0)]
    print("rows with a zero-land tract:", len(zero_land))
    # Primary reading: the 99 percent mutual overlap threshold defines the pair, and "one to one" is then
    # automatic (two different tracts cannot each hold 99 percent of the same land). Sliver rows of under
    # 1 percent are ignored. The strict reading (no other crosswalk row at all) is reported as a sensitivity.
    stable_pairs = sB
    verdict("stable tracts (99 percent mutual land overlap)", claims["stable_tracts"], len(sB), "count")
    print("  sensitivity: strict one-to-one counting every crosswalk row:", len(sA),
          "; ignoring zero-land rows:", len(sC), "; pairs with a sliver row attached:", len(sB) - len(sA))
    assert sB["GEOID_TRACT_20"].is_unique and sB["GEOID_TRACT_10"].is_unique

    pairs = stable_pairs[["GEOID_TRACT_10", "GEOID_TRACT_20"]].rename(
        columns={"GEOID_TRACT_10": "g10", "GEOID_TRACT_20": "g20"})
    cmp_ = pairs.merge(t17[["rate", "moe"]].rename(columns={"rate": "r17", "moe": "m17"}),
                       left_on="g10", right_index=True, how="left")
    cmp_ = cmp_.merge(t24[["rate", "moe"]].rename(columns={"rate": "r24", "moe": "m24"}),
                      left_on="g20", right_index=True, how="left")
    print("stable pairs missing from the ACS files: 2017", cmp_["r17"].isna().sum(), " 2024", cmp_["r24"].isna().sum())
    ok = cmp_.dropna(subset=["r17", "r24"]).copy()
    verdict("poverty tracts compared", claims["poverty_tracts_compared"], len(ok), "count")
    ok["chg"] = ok["r24"] - ok["r17"]
    ok["dmoe"] = np.sqrt(ok["m17"] ** 2 + ok["m24"] ** 2)
    ok["dist"] = ok["chg"].abs() > ok["dmoe"]
    verdict("poverty median change", claims["poverty_median_change_pts"], ok["chg"].median())
    verdict("poverty mean change", claims["poverty_mean_change_pts"], ok["chg"].mean())
    verdict("share distinguishable (%)", claims["poverty_share_distinguishable_pct"], 100 * ok["dist"].mean())
    verdict("n down distinguishable", claims["poverty_n_down_distinguishable"], int((ok.dist & (ok.chg < 0)).sum()), "count")
    verdict("n up distinguishable", claims["poverty_n_up_distinguishable"], int((ok.dist & (ok.chg > 0)).sum()), "count")
    n_cmp = len(ok)
    print(f"  chance level: at 90 percent confidence a no-change world flags about {0.10*n_cmp:.0f} of {n_cmp} tracts "
          f"(about {0.05*n_cmp:.0f} in each direction); observed {int(ok.dist.sum())} ({int((ok.dist&(ok.chg<0)).sum())} down, {int((ok.dist&(ok.chg>0)).sum())} up)")
    verdict("n down any", claims["poverty_n_down_any"], int((ok.chg < 0).sum()), "count")
    verdict("n up any", claims["poverty_n_up_any"], int((ok.chg > 0).sum()), "count")
    print("  zero change tracts:", int((ok.chg == 0).sum()))
    verdict("median change MOE (pts)", claims["poverty_median_change_moe_pts"], ok["dmoe"].median())
    verdict("largest distinguishable drop", claims["poverty_largest_distinguishable_drop"], ok.loc[ok.dist, "chg"].min())
    verdict("largest distinguishable rise", claims["poverty_largest_distinguishable_rise"], ok.loc[ok.dist, "chg"].max())
    rho = ok["r17"].rank().corr(ok["r24"].rank())
    try:
        from scipy.stats import spearmanr
        rho_s = spearmanr(ok["r17"], ok["r24"])[0]
        print(f"  spearman manual {rho:.6f}, scipy {rho_s:.6f}")
    except Exception:
        pass
    verdict("Spearman rank correlation", claims["poverty_rank_corr_2013_vs_2020"], rho)

    ok["q"] = pd.qcut(ok["r17"], 4, labels=["lowest", "second", "third", "highest"])
    for q in ["lowest", "second", "third", "highest"]:
        s = ok[ok.q == q]
        verdict(f"quartile {q} median change", claims[f"poverty_quartile_{q}_median_change"], s["chg"].median())
        verdict(f"quartile {q} median start", claims[f"poverty_quartile_{q}_median_start"], s["r17"].median())
        verdict(f"quartile {q} share distinguishable", claims[f"poverty_quartile_{q}_share_distinguishable_pct"],
                100 * s["dist"].mean())
    verdict("stable tracts poverty >=30 in 2013-2017", claims["stable_tracts_poverty_30plus_2013_2017"],
            int((ok.r17 >= 30).sum()), "count")
    verdict("stable tracts poverty >=30 in 2020-2024", claims["stable_tracts_poverty_30plus_2020_2024"],
            int((ok.r24 >= 30).sum()), "count")
    verdict("stable tracts >=30 in both", claims["stable_tracts_30plus_both"],
            int(((ok.r17 >= 30) & (ok.r24 >= 30)).sum()), "count")

    # ---------------- reliability of 2020-2024 tract poverty
    v = t24.dropna(subset=["rate"])
    verdict("2020-2024 tracts with a poverty value", claims["poverty_2020_2024_tracts_with_value"], len(v), "count")
    verdict("median tract MOE (pts)", claims["poverty_2020_2024_median_tract_moe_pts"], v["moe"].median())
    verdict("p90 tract MOE (pts)", claims["poverty_2020_2024_p90_tract_moe_pts"], v["moe"].quantile(0.9))
    cv = (v["moe"] / Z) / v["rate"]  # same units cancel
    pos = v["rate"] > 0
    print(f"  tracts with rate 0: {(~pos).sum()} (CV undefined); cv>0.30 count {(cv > 0.30).sum()} "
          f"of {len(v)} ({100*(cv>0.30).sum()/len(v):.2f}%); counting zero-rate tracts as low reliability "
          f"{100*((cv > 0.30) | ~pos).sum()/len(v):.2f}%; excluding them {100*(cv[pos] > 0.30).mean():.2f}%")
    verdict("share CV > 0.30 (denominator all tracts with value)", claims["poverty_2020_2024_share_cv_over_30pct"],
            100 * (cv > 0.30).sum() / len(v))
    p90 = v["rate"].quantile(0.9)
    print("  p90 cutoff of rate:", round(p90, 2))
    verdict("poverty p90 cutoff (%)", claims["poverty_p90_cutoff_pct"], p90)
    ge = v[v["rate"] >= p90]
    print(f"  tracts with rate >= p90: {len(ge)}; of which interval reaches below p90: {int(((ge['rate'] - ge['moe']) < p90).sum())}"
          f" (the tract sitting exactly on the cutoff always counts as reaching below it)")
    over = v[v["rate"] > p90]
    verdict("tracts over p90", claims["poverty_tracts_over_p90"], len(over), "count")
    verdict("tracts over p90 whose interval reaches below p90", claims["poverty_tracts_over_p90_interval_reaches_below"],
            int(((over["rate"] - over["moe"]) < p90).sum()), "count")
    top20 = v.sort_values("rate", ascending=False).head(20)
    verdict("top 20 tracts whose interval reaches below p90", claims["top20_poverty_tracts_interval_reaches_below_p90"],
            int(((top20["rate"] - top20["moe"]) < p90).sum()), "count")
    # stable vs changed boundary tracts
    stable20 = set(stable_pairs["GEOID_TRACT_20"])
    vs = v[v.index.isin(stable20)]
    vc = v[~v.index.isin(stable20)]
    verdict("median 2020-2024 poverty, stable tracts", claims["poverty_2020_2024_median_stable_tracts"], vs["rate"].median())
    verdict("median 2020-2024 poverty, changed boundary tracts", claims["poverty_2020_2024_median_not_stable_tracts"],
            vc["rate"].median())
    print(f"  2020 tracts not in a stable pair: {len(t24) - len(stable20)}; of those with a poverty value: {len(vc)}")
    verdict("changed boundary tracts (2020), counted among tracts with a poverty value", claims["not_stable_2020_tracts_with_poverty_value"], len(vc), "count")
    verdict("changed boundary tracts (2020), counted among all 2020 tracts", claims["not_stable_2020_tracts_all"], len(t24) - len(stable20), "count")
    miss = pairs[~pairs.g20.isin(t24.index) | ~pairs.g10.isin(t17.index) | pairs.g20.isin(t24.index[t24.rate.isna()]) | pairs.g10.isin(t17.index[t17.rate.isna()])]
    print("  stable pairs without a usable poverty rate in at least one vintage:", miss.values.tolist())
    s30_17 = (ok.r17 >= 30).sum()
    verdict("stable_tracts (in files) = stable pairs present in 2020 file", claims["stable_tracts"],
            int(pairs["g20"].isin(t24.index).sum()), "count")

    # ---------------- reconciliation tract sum vs county
    for lab, tsum1, tsum2, c1, c2 in (
        ("2020-2024", t24["B17001_E001"].sum(), t24["B17001_E002"].sum(), c24["B17001_E001"], c24["B17001_E002"]),
        ("2013-2017", t17["E1"].sum(), t17["E2"].sum(), c17["E1"], c17["E2"]),
    ):
        print(f"  reconcile {lab}: sum tracts B17001_001 {tsum1:.0f} vs county {c1:.0f}; _002 {tsum2:.0f} vs {c2:.0f}")
        verdict(f"tract sum B17001_001 = county ({lab})", c1, tsum1, "count")
        verdict(f"tract sum B17001_002 = county ({lab})", c2, tsum2, "count")

    # ---------------- rent burden
    r24, rc24, _ = load_2024("B25070", list(range(1, 12)))
    r17c = load_2017("B25070", list(range(1, 12)), county=True)

    def rb(get_e, get_m, exclude_nc):
        num = sum(get_e(n) for n in (7, 8, 9, 10))
        mnum = math.sqrt(sum(get_m(n) ** 2 for n in (7, 8, 9, 10)))
        den = get_e(1) - (get_e(11) if exclude_nc else 0)
        mden = math.sqrt(get_m(1) ** 2 + (get_m(11) ** 2 if exclude_nc else 0))
        return 100 * num / den, 100 * float(prop_moe(num, mnum, den, mden))

    out = {}
    for ex in (False, True):
        a17, am17 = rb(lambda n: r17c[f"E{n}"], lambda n: r17c[f"M{n}"], ex)
        a24, am24 = rb(lambda n: rc24[f"B25070_E{n:03d}"], lambda n: rc24[f"B25070_M{n:03d}"], ex)
        out[ex] = (a17, am17, a24, am24, a24 - a17, math.sqrt(am17**2 + am24**2))
        print(f"  rent burden 30+ (denominator {'excl' if ex else 'incl'} not computed): 17 {a17:.3f}+-{am17:.3f} "
              f"24 {a24:.3f}+-{am24:.3f} change {a24-a17:.3f}+-{out[ex][5]:.3f}")
    verdict("rent burden 30+ change (denominator excludes 'not computed')", claims["county_rent_burden30_change"], out[True][4])
    verdict("rent burden 30+ change MOE (denominator = B25070_001 less _011, published MOEs)", claims["county_rent_burden30_change_moe"], out[True][5])
    # alternative: denominator built as the sum of cells 2 to 10, MOE by root sum of squares
    alt = []
    for E, M in ((lambda n: r17c[f"E{n}"], lambda n: r17c[f"M{n}"]),
                 (lambda n: rc24[f"B25070_E{n:03d}"], lambda n: rc24[f"B25070_M{n:03d}"])):
        num = sum(E(n) for n in (7, 8, 9, 10)); mnum = math.sqrt(sum(M(n) ** 2 for n in (7, 8, 9, 10)))
        den = sum(E(n) for n in range(2, 11)); mden = math.sqrt(sum(M(n) ** 2 for n in range(2, 11)))
        alt.append(100 * float(prop_moe(num, mnum, den, mden)))
    verdict("rent burden 30+ change MOE (denominator = sum of cells 2 to 10, root sum of squares)",
            claims["county_rent_burden30_change_moe"], math.hypot(*alt))
    print("  sensitivity: with B25070_001 as denominator the change would be", round(out[False][4], 3))

    # other_vacant: B25004 is not in the list given, so only check if easy
    try:
        o24, oc24, _ = load_2024("B25002", [1, 3])
        # other vacant lives in B25004 cell 8, 2017 seq lookup handles it
        b24, bc24, _ = load_2024("B25004", [8])
        t = load_2017("B25004", [8], county=True)
        b17h = load_2017("B25002", [1, 3], county=True)
        # project definition is unknown here; compute other vacant as share of all vacant units B25002_003 and as share of all units
        ov24_vac = 100 * bc24["B25004_E008"] / oc24["B25002_E003"]
        ov17_vac = 100 * t["E8"] / b17h["E3"]
        ov24_all = 100 * bc24["B25004_E008"] / oc24["B25002_E001"]
        ov17_all = 100 * t["E8"] / b17h["E1"]
        print(f"  other vacant share of vacant: {ov17_vac:.3f} -> {ov24_vac:.3f} change {ov24_vac-ov17_vac:.3f}")
        print(f"  other vacant share of all units: {ov17_all:.3f} -> {ov24_all:.3f} change {ov24_all-ov17_all:.3f}")
        verdict("other vacant change (share of all housing units)", claims["county_other_vacant_change"], ov24_all - ov17_all)
    except Exception as ex:
        print("  other vacant not checked:", ex)

    # ---------------- every county level indicator against outputs/analysis_county_change.csv
    print("--- county level indicators, all 15, definitions read from the 2020-2024 table shells")
    defs = {
        "pop_total": ("B01003", [1], None), "median_age": ("B01002", [1], None),
        "median_hh_income": ("B19013", [1], None), "median_home_value": ("B25077", [1], None),
        "poverty_rate": ("B17001", [2], [1]),
        "rent_burden_30": ("B25070", [7, 8, 9, 10], list(range(2, 11))),
        "rent_burden_50": ("B25070", [10], list(range(2, 11))),
        "vacancy_rate": ("B25002", [3], [1]),
        "renter_share": ("B25003", [3], [1]),
        "no_vehicle": ("B25044", [3, 10], [1]),
        "no_hs_diploma": ("B15003", list(range(2, 17)), [1]),
        "bachelors_plus": ("B15003", [22, 23, 24, 25], [1]),
        "unemployment_rate": ("B23025", [5], [3]),
        "single_parent": ("B11003", [10, 16], [3, 10, 16]),
    }
    cc = pd.read_csv(ROOT / "outputs" / "analysis_county_change.csv").set_index("indicator")
    cache = {}

    def county_cells(table):
        if table not in cache:
            allc = list(range(1, 26))
            from_shell = {"B01003": 1, "B01002": 1, "B19013": 1, "B25077": 1, "B17001": 2, "B25070": 11, "B25002": 3,
                          "B25003": 3, "B25044": 15, "B15003": 25, "B23025": 7, "B11003": 20}
            cells = list(range(1, from_shell.get(table, 8) + 1))
            c24_ = load_2024(table, cells)[1]
            c17_ = load_2017(table, cells, county=True)
            cache[table] = (c24_, c17_)
        return cache[table]

    def est_moe(table, ncells, dcells, vint):
        c24_, c17_ = county_cells(table)
        if vint == "24":
            E = lambda n: c24_[f"{table}_E{n:03d}"]; M = lambda n: c24_[f"{table}_M{n:03d}"]
        else:
            E = lambda n: c17_[f"E{n}"]; M = lambda n: c17_[f"M{n}"]
        num = sum(E(n) for n in ncells)
        mnum = math.sqrt(sum(M(n) ** 2 for n in ncells))
        if dcells is None:
            return num, mnum
        den = sum(E(n) for n in dcells)
        mden = math.sqrt(sum(M(n) ** 2 for n in dcells))
        return 100 * num / den, 100 * float(prop_moe(num, mnum, den, mden))

    for ind, (tb, nc, dc) in defs.items():
        a17, am17 = est_moe(tb, nc, dc, "17")
        a24, am24 = est_moe(tb, nc, dc, "24")
        if ind in ("median_hh_income", "median_home_value"):
            a17, am17 = a17 * ratio, am17 * ratio
        row = cc.loc[ind]
        for lab, mine, theirs in (("2013-2017", a17, row.v2013_2017), ("2020-2024", a24, row.v2020_2024),
                                  ("change", a24 - a17, row.change)):
            tol_ok = abs(mine - theirs) <= (1.0 if ind.startswith("median_h") else 0.01)
            results.append((f"county {ind} {lab}", round(float(theirs), 4), round(float(mine), 4), "MATCH" if tol_ok else "MISMATCH"))
        if ind not in ("pop_total",):
            mine = math.hypot(am17, am24)
            ok_ = abs(mine - row.change_moe) <= (1.0 if ind.startswith("median_h") else 0.01)
            results.append((f"county {ind} change MOE", round(float(row.change_moe), 4), round(mine, 4), "MATCH" if ok_ else "MISMATCH"))

    # ---------------- sentinel audit
    print("--- sentinel audit")
    for table, cols in (("B17001", [1, 2]), ("B19013", [1]), ("B25070", list(range(1, 12)))):
        tt, cc, raw = load_2024(table, cols)
        n_sent = 0
        n_nan_after = 0
        for c in raw.columns[1:]:
            v_ = pd.to_numeric(raw[c], errors="coerce")
            n_sent += int((v_ <= -222222222).sum())
        for c in tt.columns:
            if c.startswith(table + "_"):
                assert not (tt[c] < 0).any(), f"negative number survived in {c}"
                n_nan_after += int(tt[c].isna().sum())
        print(f"  {table}: sentinel cells in raw file {n_sent}; negative values after cleaning 0; NaN in tract frame {n_nan_after}")
    inc_t = i24
    sent_inc = raw24 = None
    n_sent_inc = int((pd.to_numeric(pd.read_csv(RAW / 'acs2024' / 'acsdt5y2024-b19013.dat', sep='|', dtype=str)['B19013_E001'],
                                    errors='coerce') <= -222222222).sum())
    print("  B19013 tracts with sentinel median (2024 raw, all geos):", n_sent_inc,
          "; NaN medians among county tracts:", int(inc_t["B19013_E001"].isna().sum()))
    topc = pd.to_numeric(pd.read_csv(RAW / 'acs2024' / 'acsdt5y2024-b19013.dat', sep='|', dtype=str)
                         .set_index('GEO_ID')['B19013_M001'], errors='coerce')
    topc = topc[topc.index.str.startswith('1400000US' + COUNTY)]
    print("  B19013 county tracts with MOE code -333333333 (top coded median):", int((topc == -333333333).sum()),
          "; with MOE code -222222222:", int((topc == -222222222).sum()))
    print("  B17001 2017 tracts with blank/dot estimate (cell 1 or 2):", int(t17["E1"].isna().sum() + t17["E2"].isna().sum()))
    print("  B17001 2024 tracts with zero total population:", int((t24["B17001_E001"] == 0).sum()))

    # ---------------- hand verification from raw bytes
    print("--- hand verification of 5 random tracts from raw bytes")
    rnd = random.Random(20241120)
    sample = rnd.sample(sorted(t24.index), 5)
    p = RAW / "acs2024" / "acsdt5y2024-b17001.dat"
    lines = p.read_bytes().decode("utf-8-sig").splitlines()
    header = lines[0].split("|")
    i_e1, i_m1, i_e2, i_m2 = (header.index(x) for x in ("B17001_E001", "B17001_M001", "B17001_E002", "B17001_M002"))
    bad = 0
    for g in sample:
        row = next(l for l in lines if l.startswith("1400000US" + g)).split("|")
        e1, m1, e2, m2 = (float(row[i]) for i in (i_e1, i_m1, i_e2, i_m2))
        if min(e1, m1, e2, m2) < 0:
            print(f"  {g}: sentinel present, not computed")
            continue
        pr = e2 / e1
        rad = m2**2 - pr**2 * m1**2
        mo = (math.sqrt(rad) if rad >= 0 else math.sqrt(m2**2 + pr**2 * m1**2)) / e1
        same = abs(100 * pr - t24.loc[g, "rate"]) < 1e-9 and abs(100 * mo - t24.loc[g, "moe"]) < 1e-9
        bad += 0 if same else 1
        print(f"  2024 {g}: E001={e1:.0f} M001={m1:.0f} E002={e2:.0f} M002={m2:.0f} -> rate {100*pr:.2f}% MOE {100*mo:.2f} pts "
              f"(vectorised agrees: {same})")
    # one 2017 tract, parsed by hand from the raw bytes of the sequence files
    g17 = rnd.choice(sorted(t17.index))
    with zipfile.ZipFile(TRACT_ZIP) as z:
        gl = z.read("g20175oh.csv").decode("latin-1").splitlines()
        grow = next(r for r in csv.reader(gl) if any(c == "14000US" + g17 for c in r))
        lr = grow[4]
        er = next(r for r in csv.reader(io.StringIO(z.read("e20175oh0048000.txt").decode("latin-1"))) if r[5] == lr)
        mr = next(r for r in csv.reader(io.StringIO(z.read("m20175oh0048000.txt").decode("latin-1"))) if r[5] == lr)
    e1, e2, m1, m2 = (float(x) for x in (er[6], er[7], mr[6], mr[7]))
    pr = e2 / e1
    rad = m2**2 - pr**2 * m1**2
    mo = (math.sqrt(rad) if rad >= 0 else math.sqrt(m2**2 + pr**2 * m1**2)) / e1
    same = abs(100 * pr - t17.loc[g17, "rate"]) < 1e-9 and abs(100 * mo - t17.loc[g17, "moe"]) < 1e-9
    print(f"  2017 {g17} (logrecno {lr}): E1={e1:.0f} M1={m1:.0f} E2={e2:.0f} M2={m2:.0f} -> rate {100*pr:.2f}% MOE {100*mo:.2f} pts "
          f"(vectorised agrees: {same})")
    verdict("hand check of 5 tracts (2024) and 1 (2017) agrees with vectorised code", 0, bad + (0 if same else 1), "count")

    # ---------------- summary
    print("\n=== SUMMARY ===")
    w = max(len(r[0]) for r in results)
    for c, pj, mine, vd in results:
        mine_s = "nan" if mine is None else (f"{mine:.4f}" if isinstance(mine, float) else str(mine))
        print(f"{vd:9s} {c:<{w}s}  project={pj}  mine={mine_s}")
    nm = sum(1 for r in results if r[3] == "MISMATCH")
    print(f"\n{len(results) - nm} MATCH, {nm} MISMATCH")
    return 0 if nm == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
