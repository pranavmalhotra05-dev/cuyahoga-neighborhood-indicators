"""Run sql/04_checks.sql and write outputs/data_quality_report.md and .csv.
Exit code 1 if any check FAILs.

Run: python -I src/03_checks.py
"""
import sys
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent


def main():
    con = duckdb.connect(str(ROOT / "data" / "cuyahoga.duckdb"))
    con.execute((ROOT / "sql" / "04_checks.sql").read_text(encoding="utf-8"))
    df = con.execute("SELECT * FROM dq_results ORDER BY status DESC, check_id").df()
    (ROOT / "outputs").mkdir(exist_ok=True)
    df.to_csv(ROOT / "outputs" / "data_quality_results.csv", index=False)
    n = df["status"].value_counts().to_dict()
    lines = ["# Data quality report", "",
             f"Checks: {len(df)}. PASS {n.get('PASS', 0)}, FAIL {n.get('FAIL', 0)}, INFO {n.get('INFO', 0)}.", "",
             "| Status | Check | Expected | Observed |", "|---|---|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.status} | {r.description} | {r.expected} | {r.observed} |")
    (ROOT / "outputs" / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in df.itertuples():
        print(f"{r.status:5} {r.check_id}: {r.observed}")
    con.close()
    return 1 if n.get("FAIL", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
