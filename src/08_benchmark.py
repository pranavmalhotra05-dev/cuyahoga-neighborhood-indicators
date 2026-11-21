"""Benchmark the FastAPI endpoint and three direct DuckDB queries; write outputs/query_timing.md.

Run: python -I src/08_benchmark.py
Starts the app in a subprocess on a free local port, so nothing needs to be running beforehand.
"""
import http.client
import json
import platform
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cuyahoga.duckdb"
N_API = 50
N_SQL = 20

QUERIES = {
    "A. Indicator view, all tracts (v_indicator, one indicator and vintage)": """
        SELECT geoid, value, moe, cv, reliability FROM v_indicator
        WHERE indicator_id = 'poverty_rate' AND vintage = '2020-2024' AND geo_level = 'tract'""",
    "B. Change on stable tracts (v_change_stable, one indicator)": """
        SELECT geoid_2010, geoid_2020, change, change_moe, distinguishable FROM v_change_stable
        WHERE indicator_id = 'poverty_rate'""",
    "C. Join to dim_tract (names and land area, ordered by value)": """
        SELECT t.name, t.geoid, t.aland_m2, i.value, i.moe, i.reliability
        FROM v_indicator i
        JOIN dim_vintage v ON v.vintage = i.vintage
        JOIN dim_tract t ON t.geoid = i.geoid AND t.tract_vintage = v.tract_vintage
        WHERE i.indicator_id = 'poverty_rate' AND i.vintage = '2020-2024' AND i.geo_level = 'tract'
        ORDER BY i.value DESC NULLS LAST""",
}


def pct(xs, p):
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[k]


def summarize(xs):
    return {"min": min(xs), "median": statistics.median(xs), "p95": pct(xs, 95), "max": max(xs), "mean": statistics.mean(xs)}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def bench_api():
    con = duckdb.connect(str(DB), read_only=True)
    inds = [r[0] for r in con.execute("SELECT indicator_id FROM indicator_def ORDER BY 1").fetchall()]
    vints = [r[0] for r in con.execute("SELECT vintage FROM dim_vintage ORDER BY 1").fetchall()]
    con.close()
    combos = [(i, v) for i in inds for v in vints]
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-I", "-m", "uvicorn", "app:app", "--app-dir", str(ROOT / "src"),
                             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        conn = None
        for _ in range(100):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                conn.request("GET", "/api/health")
                if conn.getresponse().read():
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("server did not start")
        wall, server, size = [], [], []
        for k in range(N_API):
            ind, v = combos[k % len(combos)]
            t0 = time.perf_counter()
            conn.request("GET", f"/api/values?indicator={ind}&vintage={v}")
            r = conn.getresponse()
            body = r.read()
            wall.append((time.perf_counter() - t0) * 1000)
            assert r.status == 200, (r.status, body[:200])
            server.append(float(r.getheader("X-Query-Time-Ms")))
            size.append(len(body))
        health = []
        for _ in range(N_API):
            t0 = time.perf_counter()
            conn.request("GET", "/api/health")
            conn.getresponse().read()
            health.append((time.perf_counter() - t0) * 1000)
        return summarize(wall), summarize(server), summarize(health), statistics.mean(size), combos
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def bench_sql():
    out = {}
    for name, q in QUERIES.items():
        con = duckdb.connect(str(DB), read_only=True)
        times, nrows = [], 0
        for _ in range(N_SQL):
            t0 = time.perf_counter()
            nrows = len(con.execute(q).fetchall())
            times.append((time.perf_counter() - t0) * 1000)
        con.close()
        out[name] = (times, nrows)
    return out


def f(x):
    return f"{x:.2f}"


def main():
    con = duckdb.connect(str(DB), read_only=True)
    fact_rows = con.execute("SELECT count(*) FROM fact_acs").fetchone()[0]
    n_tract = con.execute("SELECT count(DISTINCT geoid) FROM fact_acs WHERE geo_level = 'tract'").fetchone()[0]
    ver = duckdb.__version__
    con.close()

    wall, server, health, avg_size, combos = bench_api()
    sql = bench_sql()

    L = ["# Query timing", "",
         "Measured by `src/08_benchmark.py` on this machine. All times are in milliseconds.", "",
         f"- Platform: {platform.platform()}, Python {platform.python_version()}, DuckDB {ver}",
         f"- Database: `data/cuyahoga.duckdb`, {fact_rows:,} fact rows, {n_tract} distinct tract identifiers across both tract geographies",
         "",
         "**Limit of these numbers.** The database is small (about " + f"{round(fact_rows, -3) // 1000} thousand" +
         " fact rows, " + f"{DB.stat().st_size / 1e6:.1f} MB on disk" + "). These timings show that this project is responsive; they say little about how "
         "the same design would behave on a large database, where indexing, partitioning, memory and concurrency "
         "would dominate and would have to be measured again.", "",
         f"## FastAPI endpoint, {N_API} sequential requests over one keep-alive connection", "",
         f"Requests cycle through all {len(combos)} indicator and vintage combinations of `/api/values` "
         f"(average response {avg_size / 1024:.1f} KB). Client-side wall time includes HTTP, JSON serialisation "
         "and the query; the server query time is reported by the endpoint itself (header `X-Query-Time-Ms`).", "",
         "| Measure | min | median | p95 | max | mean |", "|---|---|---|---|---|---|"]
    for label, s in (("/api/values wall time (client)", wall), ("/api/values query time (server)", server),
                     (f"/api/health wall time ({N_API} requests)", health)):
        L.append(f"| {label} | {f(s['min'])} | {f(s['median'])} | {f(s['p95'])} | {f(s['max'])} | {f(s['mean'])} |")
    L += ["", f"## Direct DuckDB queries, {N_SQL} runs each (read-only connection, run 1 is cold)", "",
          "| Query | rows | run 1 | median | p95 | min | max |", "|---|---|---|---|---|---|---|"]
    for name, (times, nrows) in sql.items():
        s = summarize(times)
        L.append(f"| {name} | {nrows} | {f(times[0])} | {f(s['median'])} | {f(s['p95'])} | {f(s['min'])} | {f(s['max'])} |")
    L += ["", "The views compute every indicator from `fact_acs` at query time (no materialised table), so these "
          "numbers include the margin of error propagation and reliability classification.", ""]
    text = "\n".join(L)
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "query_timing.md").write_text(text, encoding="utf-8")
    print(text)
    print(json.dumps({"api_wall_median": wall["median"], "api_wall_p95": wall["p95"]}))


if __name__ == "__main__":
    main()
