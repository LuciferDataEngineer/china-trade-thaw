"""DuckLake catalog in Postgres, data files on an S3-compatible store.

Each ABS country-total release is one snapshot. Time travel reads the earlier
release back after the later release has replaced it.
"""

from __future__ import annotations

from pathlib import Path

import boto3
import duckdb
from botocore.client import Config


def publish_vintages(
    *,
    pg_host: str,
    pg_port: int,
    pg_user: str,
    pg_password: str,
    pg_database: str,
    s3_endpoint: str,
    s3_access: str,
    s3_secret: str,
    bucket: str,
    vintage_parquet: Path,
) -> dict:
    _ensure_bucket(s3_endpoint, s3_access, s3_secret, bucket)
    con = duckdb.connect()
    con.execute(
        "INSTALL ducklake; LOAD ducklake; INSTALL postgres; LOAD postgres; INSTALL httpfs; LOAD httpfs;"
    )
    endpoint = s3_endpoint.replace("http://", "").replace("https://", "")
    con.execute(
        f"""
        CREATE OR REPLACE SECRET s3_lake (
            TYPE s3,
            KEY_ID '{s3_access}',
            SECRET '{s3_secret}',
            ENDPOINT '{endpoint}',
            URL_STYLE 'path',
            USE_SSL false,
            REGION 'us-east-1'
        );
        CREATE OR REPLACE SECRET pg_lake (
            TYPE postgres,
            HOST '{pg_host}',
            PORT {int(pg_port)},
            DATABASE '{pg_database}',
            USER '{pg_user}',
            PASSWORD '{pg_password}'
        );
        """
    )
    con.execute(
        f"""
        ATTACH 'ducklake:postgres:dbname={pg_database}' AS lake (
            META_SECRET 'pg_lake',
            DATA_PATH 's3://{bucket}/ducklake/',
            DATA_INLINING_ROW_LIMIT 0,
            OVERRIDE_DATA_PATH true
        );
        USE lake;
        CREATE SCHEMA IF NOT EXISTS bronze;
        DROP TABLE IF EXISTS bronze.country_month;
        CREATE TABLE bronze.country_month (
            country VARCHAR,
            month DATE,
            aud_million DOUBLE
        );
        """
    )
    path = vintage_parquet.as_posix()
    con.execute(
        f"""
        INSERT INTO bronze.country_month
        SELECT country_name, CAST(period AS DATE), aud_million
        FROM read_parquet('{path}')
        WHERE vintage = '2026-08'
        """
    )
    august = _latest_snapshot(con)
    con.execute("DELETE FROM bronze.country_month")
    con.execute(
        f"""
        INSERT INTO bronze.country_month
        SELECT country_name, CAST(period AS DATE), aud_million
        FROM read_parquet('{path}')
        WHERE vintage = '2026-09'
        """
    )
    september = _latest_snapshot(con)
    china_august = con.execute(
        f"""
        SELECT month, aud_million
        FROM bronze.country_month AT (VERSION => {august})
        WHERE country LIKE 'China (excludes%'
        ORDER BY month
        """
    ).fetchall()
    china_latest = con.execute(
        """
        SELECT month, aud_million
        FROM bronze.country_month
        WHERE country LIKE 'China (excludes%'
        ORDER BY month
        """
    ).fetchall()
    objects = _list_objects(s3_endpoint, s3_access, s3_secret, bucket)
    con.close()
    return {
        "august_snapshot": august,
        "september_snapshot": september,
        "china_august_rows": len(china_august),
        "china_latest_rows": len(china_latest),
        "china_august": [(row[0].isoformat(), row[1]) for row in china_august],
        "objects": len(objects),
    }


def _latest_snapshot(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT max(snapshot_id) FROM ducklake_snapshots('lake')").fetchone()
    return int(row[0])


def _ensure_bucket(endpoint: str, access: str, secret: str, bucket: str) -> None:
    import time

    client = _s3(endpoint, access, secret)
    last_error: Exception | None = None
    for attempt in range(15):
        try:
            existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
            return
        except Exception as exc:  # noqa: BLE001 - the store may still be starting
            last_error = exc
            time.sleep(2)
    raise RuntimeError("object store did not accept a bucket") from last_error


def _list_objects(endpoint: str, access: str, secret: str, bucket: str) -> list[str]:
    client = _s3(endpoint, access, secret)
    found = []
    token = None
    while True:
        kwargs = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        found.extend(item["Key"] for item in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return found
        token = page.get("NextContinuationToken")


def _s3(endpoint: str, access: str, secret: str):
    url = endpoint if endpoint.startswith("http") else f"http://{endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=url,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
