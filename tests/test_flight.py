import socket
from pathlib import Path

import duckdb

from china_trade.flight_server import query, serve_in_thread


def test_flight_serves_a_gold_select(tmp_path: Path):
    db = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA gold")
    con.execute("CREATE TABLE gold.state_shock (state_code VARCHAR, shock_aud DOUBLE)")
    con.execute("INSERT INTO gold.state_shock VALUES ('5', 13.6e9), ('3', 2.4e9)")
    con.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    location = f"grpc://127.0.0.1:{port}"
    server = serve_in_thread(db, location)
    try:
        table = query(
            location, "SELECT state_code, shock_aud FROM gold.state_shock ORDER BY shock_aud DESC"
        )
    finally:
        server.shutdown()
    assert table.column("state_code").to_pylist() == ["5", "3"]
    assert table.column("shock_aud")[0].as_py() == 13.6e9


def test_flight_rejects_a_write(tmp_path: Path):

    db = tmp_path / "warehouse.duckdb"
    duckdb.connect(str(db)).execute("CREATE TABLE gold_dummy (n INTEGER)").close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    location = f"grpc://127.0.0.1:{port}"
    server = serve_in_thread(db, location)
    try:
        with pytest_raises_flight():
            query(location, "DROP TABLE gold_dummy")
    finally:
        server.shutdown()


def pytest_raises_flight():
    import pyarrow.flight as flight
    import pytest

    return pytest.raises(flight.FlightUnauthenticatedError)
