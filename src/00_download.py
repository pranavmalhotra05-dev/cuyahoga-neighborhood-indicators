"""Download every raw input from public Census Bureau servers and write a manifest.

Run: python -I src/00_download.py
Raw files go to data_raw/ (not committed). The manifest (data/source_manifest.csv)
records URL, size, SHA-256 and download date, and is committed.
"""
import csv, hashlib, sys, datetime, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
SF = "https://www2.census.gov/programs-surveys/acs/summary_file"
TABLES = ["b01002", "b01003", "b11003", "b15003", "b17001", "b19013", "b23025",
          "b25002", "b25003", "b25004", "b25044", "b25070", "b25077"]

FILES = []
# Vintage 2020-2024 (ACS 5-year, 2020 tract geography), table-based summary file
for t in TABLES:
    FILES.append((f"acs2024/acsdt5y2024-{t}.dat", f"{SF}/2024/table-based-SF/data/5YRData/acsdt5y2024-{t}.dat"))
FILES.append(("acs2024/Geos20245YR.txt", f"{SF}/2024/table-based-SF/documentation/Geos20245YR.txt"))
FILES.append(("acs2024/ACS20245YR_Table_Shells.txt", f"{SF}/2024/table-based-SF/documentation/ACS20245YR_Table_Shells.txt"))
# Vintage 2013-2017 (ACS 5-year, 2010 tract geography), classic summary file, Ohio tracts and block groups
FILES.append(("acs2017/Ohio_Tracts_Block_Groups_Only.zip", f"{SF}/2017/data/5_year_by_state/Ohio_Tracts_Block_Groups_Only.zip"))
FILES.append(("acs2017/Ohio_All_Geographies_Not_Tracts_Block_Groups.zip", f"{SF}/2017/data/5_year_by_state/Ohio_All_Geographies_Not_Tracts_Block_Groups.zip"))
FILES.append(("acs2017/2017_5yr_Summary_FileTemplates.zip", f"{SF}/2017/data/2017_5yr_Summary_FileTemplates.zip"))
FILES.append(("acs2017/ACS_5yr_Seq_Table_Number_Lookup.txt", f"{SF}/2017/documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt"))
# Boundaries and crosswalk
FILES.append(("tiger/tl_2017_39_tract.zip", "https://www2.census.gov/geo/tiger/TIGER2017/TRACT/tl_2017_39_tract.zip"))
FILES.append(("tiger/tl_2024_39_tract.zip", "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_39_tract.zip"))
FILES.append(("tiger/tl_2024_us_county.zip", "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip"))
FILES.append(("xwalk/tab20_tract20_tract10_natl.txt", "https://www2.census.gov/geo/docs/maps-data/data/rel2020/tract/tab20_tract20_tract10_natl.txt"))


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(rel, url):
    dest = RAW / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest, False
    req = urllib.request.Request(url, headers={"User-Agent": "cuyahoga-neighborhood-indicators/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    return dest, True


def fetch_cpi():
    """CPI-U (all items, U.S. city average, not seasonally adjusted) annual averages from the BLS public API.
    Used only to express 2013-2017 dollars in 2024 dollars."""
    import json
    body = json.dumps({"seriesid": ["CUUR0000SA0"], "startyear": "2017", "endyear": "2024", "annualaverage": True}).encode()
    req = urllib.request.Request("https://api.bls.gov/publicAPI/v1/timeseries/data/", data=body,
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    rows = [(r["year"], r["value"]) for r in d["Results"]["series"][0]["data"] if r["period"] == "M13"]
    with open(ROOT / "data" / "cpi_u_annual.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "cpi_u_annual_avg", "source", "retrieved"])
        for y, v in sorted(rows):
            w.writerow([y, v, "BLS series CUUR0000SA0 via api.bls.gov/publicAPI/v1", datetime.date.today().isoformat()])


def main():
    if not (ROOT / "data" / "cpi_u_annual.csv").exists():
        fetch_cpi()
    rows = []
    for rel, url in FILES:
        for attempt in range(3):
            try:
                dest, new = fetch(rel, url)
                break
            except (urllib.error.URLError, TimeoutError) as e:
                print("retry", rel, e, file=sys.stderr)
        else:
            sys.exit(f"failed: {url}")
        rows.append({"file": rel, "url": url, "bytes": dest.stat().st_size,
                     "sha256": sha256(dest), "downloaded": datetime.date.today().isoformat()})
        print(("downloaded " if new else "have ") + rel, dest.stat().st_size)
    out = ROOT / "data" / "source_manifest.csv"
    prev = {}
    if out.exists():
        with open(out, newline="") as f:
            prev = {r["file"]: r for r in csv.DictReader(f)}
    for r in rows:  # keep the original download date if the file was already present
        if r["file"] in prev and prev[r["file"]]["sha256"] == r["sha256"]:
            r["downloaded"] = prev[r["file"]]["downloaded"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
