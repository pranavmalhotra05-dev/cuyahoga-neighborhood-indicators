"""Small FastAPI app: serves web/ statically and exposes live DuckDB queries.

Run: python -I -m uvicorn app:app --app-dir src --host 127.0.0.1 --port 8000
or:  bash scripts/run_server.sh

Endpoints:
  GET /api/health
  GET /api/indicators
  GET /api/values?indicator=poverty_rate&vintage=2020-2024
The values endpoint returns the server-side query time in the X-Query-Time-Ms header
and as query_ms in the JSON body.
"""
import time
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cuyahoga.duckdb"
WEB = ROOT / "web"
ROUND_BY_KIND = {"count": 0, "rate": 2, "median_dollars": 0, "median_other": 1}

app = FastAPI(title="Cuyahoga neighborhood indicators", version="1.0")
_con = duckdb.connect(str(DB), read_only=True)


def cursor():
    return _con.cursor()


def clean(x, nd):
    if x is None or x != x:
        return None
    return int(round(x)) if nd == 0 else round(float(x), nd)


@app.get("/api/health")
def health():
    t0 = time.perf_counter()
    n = cursor().execute("SELECT count(*) FROM fact_acs").fetchone()[0]
    return {"status": "ok", "database": DB.name, "fact_rows": n,
            "query_ms": round((time.perf_counter() - t0) * 1000, 3)}


@app.get("/api/indicators")
def indicators():
    cur = cursor()
    rows = cur.execute("""SELECT indicator_id, name, kind, unit, higher_is, theme, definition
                          FROM indicator_def ORDER BY theme, indicator_id""").fetchall()
    vint = cur.execute("SELECT vintage, tract_vintage, dollar_year FROM dim_vintage ORDER BY vintage").fetchall()
    return {"indicators": [dict(zip(["id", "name", "kind", "unit", "higher_is", "theme", "definition"], r)) for r in rows],
            "vintages": [dict(zip(["id", "tract_vintage", "dollar_year"], r)) for r in vint]}


@app.get("/api/values")
def values(response: Response, indicator: str = Query(...), vintage: str = Query(...)):
    cur = cursor()
    kind = cur.execute("SELECT kind FROM indicator_def WHERE indicator_id = ?", [indicator]).fetchone()
    if not kind:
        raise HTTPException(404, f"unknown indicator: {indicator}")
    if not cur.execute("SELECT 1 FROM dim_vintage WHERE vintage = ?", [vintage]).fetchone():
        raise HTTPException(404, f"unknown vintage: {vintage}")
    nd = ROUND_BY_KIND[kind[0]]
    t0 = time.perf_counter()
    rows = cur.execute("""SELECT geoid, value, moe, reliability FROM v_indicator
                          WHERE indicator_id = ? AND vintage = ? AND geo_level = 'tract'""",
                       [indicator, vintage]).fetchall()
    query_ms = (time.perf_counter() - t0) * 1000
    vals = {g: [clean(v, nd), clean(m, nd), rel] for g, v, m, rel in rows}
    response.headers["X-Query-Time-Ms"] = f"{query_ms:.3f}"
    return {"indicator": indicator, "vintage": vintage, "n": len(vals),
            "query_ms": round(query_ms, 3), "values": vals}


@app.get("/")
def root():
    return RedirectResponse("/index.html?api=1")


app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
