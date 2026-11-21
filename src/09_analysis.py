"""Analysis: how did tract-level poverty (and companions) change between ACS 2013-2017 and
2020-2024 in Cuyahoga County, and how much do the margins of error leave unsaid?

Only tracts with essentially unchanged boundaries (v_stable_tract) are compared tract by tract.
Writes outputs/analysis_numbers.json, outputs/analysis_tables.csv, outputs/analysis.md and
docs/img/poverty_change.png. Every figure in the markdown is computed here.

Run: python -I src/09_analysis.py
"""
import json
from pathlib import Path
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "data" / "cuyahoga.duckdb"), read_only=True)
N = {}


def q(sql):
    return con.execute(sql).df()


# 1. County level, where the sample is large
cty = q("""SELECT indicator_id, vintage, value_2024usd AS value, moe_2024usd AS moe
           FROM v_indicator_adj WHERE geo_level = 'county'""")
rows = []
for ind, g in cty.groupby("indicator_id"):
    a = g[g.vintage == "2013-2017"].iloc[0]
    b = g[g.vintage == "2020-2024"].iloc[0]
    d = b.value - a.value
    m = float(np.sqrt(a.moe ** 2 + b.moe ** 2))
    rows.append({"indicator": ind, "v2013_2017": a.value, "moe2013_2017": a.moe, "v2020_2024": b.value,
                 "moe2020_2024": b.moe, "change": d, "change_moe": m, "distinguishable": abs(d) > m})
county = pd.DataFrame(rows)
county.to_csv(ROOT / "outputs" / "analysis_county_change.csv", index=False)
cp = county.set_index("indicator")
N["county_poverty_2013_2017"] = round(cp.loc["poverty_rate", "v2013_2017"], 2)
N["county_poverty_2013_2017_moe"] = round(cp.loc["poverty_rate", "moe2013_2017"], 2)
N["county_poverty_2020_2024"] = round(cp.loc["poverty_rate", "v2020_2024"], 2)
N["county_poverty_2020_2024_moe"] = round(cp.loc["poverty_rate", "moe2020_2024"], 2)
N["county_poverty_change"] = round(cp.loc["poverty_rate", "change"], 2)
N["county_poverty_change_moe"] = round(cp.loc["poverty_rate", "change_moe"], 2)
N["county_income_2013_2017_in_2024usd"] = round(cp.loc["median_hh_income", "v2013_2017"])
N["county_income_2020_2024"] = round(cp.loc["median_hh_income", "v2020_2024"])
N["county_income_change_real"] = round(cp.loc["median_hh_income", "change"])
N["county_income_change_real_moe"] = round(cp.loc["median_hh_income", "change_moe"])
N["county_rent_burden30_change"] = round(cp.loc["rent_burden_30", "change"], 2)
N["county_rent_burden30_change_moe"] = round(cp.loc["rent_burden_30", "change_moe"], 2)
N["county_other_vacant_change"] = round(cp.loc["other_vacant", "change"], 2)
N["county_other_vacant_change_moe"] = round(cp.loc["other_vacant", "change_moe"], 2)

# 2. Tract level on stable tracts
ch = q("SELECT * FROM v_change_stable")
N["stable_tracts"] = int(q("SELECT count(*) AS n FROM v_stable_tract").n[0])
N["tracts_2010"] = int(q("SELECT count(*) AS n FROM dim_tract WHERE tract_vintage = 2010").n[0])
N["tracts_2020"] = int(q("SELECT count(*) AS n FROM dim_tract WHERE tract_vintage = 2020").n[0])
summ = []
for ind, g in ch.groupby("indicator_id"):
    summ.append({"indicator": ind, "tracts_compared": len(g), "median_change": g.change.median(),
                 "mean_change": g.change.mean(),
                 "share_distinguishable": g.distinguishable.mean(),
                 "n_up_distinguishable": int(((g.change > 0) & g.distinguishable).sum()),
                 "n_down_distinguishable": int(((g.change < 0) & g.distinguishable).sum()),
                 "median_change_moe": g.change_moe.median()})
summ = pd.DataFrame(summ).sort_values("indicator")
summ.to_csv(ROOT / "outputs" / "analysis_tract_change_summary.csv", index=False)
p = ch[ch.indicator_id == "poverty_rate"].sort_values("geoid_2020").reset_index(drop=True)
N["poverty_tracts_compared"] = len(p)
N["poverty_median_change_pts"] = round(p.change.median(), 2)
N["poverty_mean_change_pts"] = round(p.change.mean(), 2)
N["poverty_share_distinguishable_pct"] = round(100 * p.distinguishable.mean(), 1)
N["poverty_n_down_distinguishable"] = int(((p.change < 0) & p.distinguishable).sum())
N["poverty_n_up_distinguishable"] = int(((p.change > 0) & p.distinguishable).sum())
N["poverty_n_down_any"] = int((p.change < 0).sum())
N["poverty_n_up_any"] = int((p.change > 0).sum())
N["poverty_median_change_moe_pts"] = round(p.change_moe.median(), 2)
N["poverty_largest_distinguishable_drop"] = round(p[p.distinguishable].change.min(), 1)
N["poverty_largest_distinguishable_rise"] = round(p[p.distinguishable].change.max(), 1)

# Regression to the mean check: do tracts that were poorest fall most, even for noise?
p["q2013"] = pd.qcut(p.value_2013_2017, 4, labels=["lowest", "second", "third", "highest"])
byq = p.groupby("q2013", observed=True).agg(tracts=("change", "size"), median_poverty_2013_2017=("value_2013_2017", "median"),
                                          median_change=("change", "median"),
                                          share_distinguishable=("distinguishable", "mean")).reset_index()
byq.to_csv(ROOT / "outputs" / "analysis_poverty_change_by_quartile.csv", index=False)
for r in byq.itertuples():
    N[f"poverty_quartile_{r.q2013}_median_change"] = round(r.median_change, 2)
    N[f"poverty_quartile_{r.q2013}_median_start"] = round(r.median_poverty_2013_2017, 1)
    N[f"poverty_quartile_{r.q2013}_share_distinguishable_pct"] = round(100 * r.share_distinguishable, 1)
N["poverty_rank_corr_2013_vs_2020"] = round(p.value_2013_2017.corr(p.value_2020_2024, method="spearman"), 3)


# Regression to the mean under a no-true-change assumption. Treat the 2013-2017 estimates as the truth,
# add independent sampling noise (sd = MOE / 1.645) to build a fake "2013-2017" and "2020-2024" pair,
# split by the fake 2013-2017 value and look at median change per quartile. Heuristic: the truth is
# itself noisy, so this is an approximation of the size of the artifact, not a correction.
rng = np.random.default_rng(20)
se13 = (p.change_moe ** 2 / 2) ** 0.5 / 1.645  # equal split of the difference variance
truth = p.value_2013_2017.values
sims = []
for _ in range(500):
    a = truth + rng.normal(0, se13.values)
    b = truth + rng.normal(0, se13.values)
    qs = pd.qcut(a, 4, labels=False)
    sims.append([np.median((b - a)[qs == k]) for k in range(4)])
sims = np.array(sims).mean(axis=0)
for k, name in enumerate(q_order_names := ["lowest", "second", "third", "highest"]):
    N[f"poverty_quartile_{name}_artifact_median_change_if_no_true_change"] = round(float(sims[k]), 2)

# High poverty tracts (30 percent or more) in each vintage, stable tracts only
hi13 = (p.value_2013_2017 >= 30).sum()
hi20 = (p.value_2020_2024 >= 30).sum()
N["stable_tracts_poverty_30plus_2013_2017"] = int(hi13)
N["stable_tracts_poverty_30plus_2020_2024"] = int(hi20)
N["stable_tracts_30plus_both"] = int(((p.value_2013_2017 >= 30) & (p.value_2020_2024 >= 30)).sum())

# 3. How much uncertainty a single tract estimate carries
v = q("""SELECT * FROM v_indicator WHERE geo_level = 'tract' AND indicator_id = 'poverty_rate'
         AND vintage = '2020-2024' AND value IS NOT NULL AND moe IS NOT NULL""")
N["poverty_2020_2024_tracts_with_value"] = len(v)
N["poverty_2020_2024_median_tract_moe_pts"] = round(v.moe.median(), 1)
N["poverty_2020_2024_p90_tract_moe_pts"] = round(v.moe.quantile(0.9), 1)
N["poverty_2020_2024_share_cv_over_30pct"] = round(100 * (v.cv > 0.30).mean(), 1)
rel = q("""SELECT indicator_id, reliability, count(*) AS n FROM v_indicator WHERE geo_level = 'tract'
           AND vintage = '2020-2024' GROUP BY ALL""")
relp = rel.pivot(index="indicator_id", columns="reliability", values="n").fillna(0).astype(int)
relp.to_csv(ROOT / "outputs" / "analysis_reliability_by_indicator.csv")

# Rank uncertainty: among the 20 tracts with the highest poverty estimate in 2020-2024, how many have a
# 90 percent interval that reaches below the 90th percentile of all tract estimates?
cut = v.value.quantile(0.90)
top = v.sort_values("value", ascending=False).head(20)
N["poverty_p90_cutoff_pct"] = round(cut, 1)
N["top20_poverty_tracts_interval_reaches_below_p90"] = int(((top.value - top.moe) < cut).sum())
N["poverty_tracts_over_p90_interval_reaches_below"] = int(((v[v.value >= cut].value - v[v.value >= cut].moe) < cut).sum())
N["poverty_tracts_over_p90"] = int((v.value >= cut).sum())

# 4. Stable versus non-stable tracts (are the compared tracts representative?)
st = q("""SELECT t.geoid, (s.geoid_2020 IS NOT NULL) AS stable, i.value
          FROM dim_tract t LEFT JOIN v_stable_tract s ON s.geoid_2020 = t.geoid
          JOIN v_indicator i ON i.geoid = t.geoid AND i.vintage = '2020-2024' AND i.indicator_id = 'poverty_rate'
          WHERE t.tract_vintage = 2020 AND i.value IS NOT NULL""")
N["poverty_2020_2024_median_stable_tracts"] = round(st[st.stable].value.median(), 1)
N["poverty_2020_2024_median_not_stable_tracts"] = round(st[~st.stable].value.median(), 1)
N["not_stable_2020_tracts_with_poverty_value"] = int((~st.stable).sum())
N["not_stable_2020_tracts_all"] = int(q("SELECT count(*) AS n FROM dim_tract WHERE tract_vintage = 2020 AND geoid NOT IN (SELECT geoid_2020 FROM v_stable_tract)").n[0])

# 5. Chart
fig, ax = plt.subplots(1, 2, figsize=(11.5, 5.2))
sig = p.distinguishable
ax[0].errorbar(p.value_2013_2017[~sig], p.value_2020_2024[~sig], fmt="o", ms=3, color="#9aa5b1", alpha=0.7,
               label="change within margin of error")
ax[0].errorbar(p.value_2013_2017[sig & (p.change < 0)], p.value_2020_2024[sig & (p.change < 0)], fmt="o", ms=3.5,
               color="#1b7f79", label="lower (distinguishable)")
ax[0].errorbar(p.value_2013_2017[sig & (p.change > 0)], p.value_2020_2024[sig & (p.change > 0)], fmt="o", ms=3.5,
               color="#c2410c", label="higher (distinguishable)")
ax[0].plot([0, 80], [0, 80], color="#333", lw=0.8)
ax[0].set_xlabel("Poverty rate 2013-2017 (%)")
ax[0].set_ylabel("Poverty rate 2020-2024 (%)")
ax[0].set_title(f"{len(p)} tracts with unchanged boundaries")
ax[0].legend(frameon=False, fontsize=8, loc="upper left")
q_order = ["lowest", "second", "third", "highest"]
data = [p[p.q2013 == k].change.values for k in q_order]
ax[1].boxplot(data, tick_labels=[f"{k}\n(median {p[p.q2013 == k].value_2013_2017.median():.0f}%)" for k in q_order], showfliers=True,
              flierprops={"markersize": 3, "alpha": 0.5})
ax[1].axhline(0, color="#333", lw=0.8)
ax[1].set_xlabel("Quartile of 2013-2017 poverty rate")
ax[1].set_ylabel("Change in poverty rate (percentage points)")
ax[1].set_title("Change by starting quartile")
fig.suptitle("Cuyahoga County tract poverty, ACS 2013-2017 to 2020-2024", fontsize=11)
fig.text(0.01, 0.01, "Source: ACS 5-year table B17001. Stable tracts only. Distinguishable means |change| exceeds the 90% margin of error of the difference.",
         fontsize=7, color="#555")
fig.tight_layout(rect=(0, 0.03, 1, 0.96))
fig.savefig(ROOT / "docs" / "img" / "poverty_change.png", dpi=110)

(ROOT / "outputs" / "analysis_numbers.json").write_text(json.dumps(N, indent=1), encoding="utf-8")
print(json.dumps(N, indent=1))
print(county.round(2).to_string())
print(summ.round(2).to_string())
print(byq.round(2).to_string())
print(relp.to_string())
