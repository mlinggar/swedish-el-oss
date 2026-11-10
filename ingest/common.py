"""Shared ingest plumbing: env, DB connection, HTTP fetch, raw upsert."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
USER_AGENT = "swedish-el-oss/1.0 (personal research)"


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def get_conn():
    load_env()
    kwargs = {"dbname": os.environ.get("PGDATABASE", "swedish_el"),
              "user": os.environ.get("PGUSER", "mlinggar")}
    if os.environ.get("PGHOST"):
        kwargs["host"] = os.environ["PGHOST"]
        kwargs["port"] = os.environ.get("PGPORT", "5432")
    return psycopg2.connect(**kwargs)


def fetch(url, method="GET", body=None, headers=None, timeout=90, retries=3):
    """GET/POST with exponential backoff; strips a UTF-8 BOM. Returns text."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            if method.upper() == "POST":
                r = requests.post(url, data=body, headers=hdrs, timeout=timeout)
            else:
                r = requests.get(url, headers=hdrs, timeout=timeout)
            r.raise_for_status()
            return r.text.lstrip("\ufeff")
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise last


def upsert_raw(conn, table, input_file_name, load_tier, payload):
    """Append one raw row. Idempotency key is (input_file_name, file_modification_time)
    where file_modification_time is the fetch timestamp, so each fetch is a new
    version and silver's file_modification_time DESC dedup keeps the newest."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"_raw_text": payload}
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO raw.{table} "
            "(input_file_name, file_modification_time, load_tier, payload) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (input_file_name, file_modification_time) DO NOTHING",
            (input_file_name, datetime.now(timezone.utc), load_tier, Json(payload)))
    conn.commit()


def run_requests(conn, table, reqs, load_tier, pause=0.0):
    ok = 0
    for r in reqs:
        text = fetch(r["url"], r.get("method", "GET"), r.get("body"), r.get("headers"))
        upsert_raw(conn, table, r["input_file_name"], load_tier, text)
        ok += 1
        print(f"  + {r['input_file_name']}")
        if pause:
            time.sleep(pause)
    return ok
