import os
import shutil
from pathlib import Path

import duckdb
import pytest

from china_trade.lake import publish_vintages

ROOT = Path(__file__).resolve().parents[1]
VINTAGE = ROOT / "data" / "snapshot" / "country_vintage.parquet"


pytestmark = pytest.mark.lake


def _china_august():
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT CAST(period AS DATE), aud_million
        FROM read_parquet('{VINTAGE.as_posix()}')
        WHERE vintage = '2026-08' AND country_name LIKE 'China (excludes%'
        ORDER BY period
        """
    ).fetchall()
    con.close()
    return [(row[0].isoformat(), row[1]) for row in rows]


def _assert_time_travel(result: dict) -> None:
    assert result["september_snapshot"] > result["august_snapshot"]
    assert result["objects"] > 0
    assert result["china_august"] == _china_august()
    august = dict(result["china_august"])
    assert abs(august["2026-08-01"] - 16069) < 1
    assert abs(august["2024-06-01"] - 15823) < 1


@pytest.mark.skipif(
    not os.environ.get("LAKE_PG_HOST"), reason="service containers are not configured"
)
def test_service_containers_time_travel():
    result = publish_vintages(
        pg_host=os.environ["LAKE_PG_HOST"],
        pg_port=int(os.environ.get("LAKE_PG_PORT", "5432")),
        pg_user="postgres",
        pg_password="postgres",
        pg_database="ducklake",
        s3_endpoint=os.environ["LAKE_S3_ENDPOINT"],
        s3_access="rustfsadmin",
        s3_secret="rustfsadmin",
        bucket="trade-lake",
        vintage_parquet=VINTAGE,
    )
    _assert_time_travel(result)


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required")
def test_testcontainers_time_travel():
    from testcontainers.core.container import DockerContainer
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:16-alpine", username="postgres", password="postgres", dbname="ducklake"
    ) as postgres:
        rustfs = (
            DockerContainer("rustfs/rustfs:latest")
            .with_env("RUSTFS_ACCESS_KEY", "rustfsadmin")
            .with_env("RUSTFS_SECRET_KEY", "rustfsadmin")
            .with_env("RUSTFS_ADDRESS", "0.0.0.0:9000")
            .with_env("RUSTFS_VOLUMES", "/data")
            .with_exposed_ports(9000)
        )
        rustfs.start()
        try:
            host = rustfs.get_container_host_ip()
            port = rustfs.get_exposed_port(9000)
            result = publish_vintages(
                pg_host=postgres.get_container_host_ip(),
                pg_port=int(postgres.get_exposed_port(5432)),
                pg_user="postgres",
                pg_password="postgres",
                pg_database="ducklake",
                s3_endpoint=f"http://{host}:{port}",
                s3_access="rustfsadmin",
                s3_secret="rustfsadmin",
                bucket="trade-lake",
                vintage_parquet=VINTAGE,
            )
        finally:
            rustfs.stop()
    _assert_time_travel(result)
