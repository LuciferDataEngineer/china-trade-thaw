"""Arrow Flight endpoint over a DuckDB file of gold tables.

Tickets are a single read-only SELECT. The integration test asks for rows.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import duckdb
import pyarrow.flight as flight

_FORBIDDEN = re.compile(
    r"\b(attach|copy|install|load|pragma|drop|insert|update|delete|create|alter|export)\b",
    re.IGNORECASE,
)


class GoldFlightServer(flight.FlightServerBase):
    def __init__(self, db_path: Path, location: str):
        super().__init__(location)
        self.db_path = str(db_path)

    def do_get(self, context, ticket):
        sql = ticket.ticket.decode("utf-8").strip().rstrip(";")
        if not _allowed(sql):
            raise flight.FlightUnauthenticatedError(
                "only a single read of the gold tables is served"
            )
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            result = con.execute(sql)
            table = result.to_arrow_table()
        finally:
            con.close()
        return flight.RecordBatchStream(table)


def _allowed(sql: str) -> bool:
    if ";" in sql or not sql.lower().startswith("select"):
        return False
    return _FORBIDDEN.search(sql) is None


def serve_in_thread(db_path: Path, location: str) -> GoldFlightServer:
    server = GoldFlightServer(db_path, location)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(location.rsplit(":", 1)[-1])), 0.2):
                return server
        except OSError:
            time.sleep(0.05)
    return server


def query(location: str, sql: str):
    client = flight.FlightClient(location)
    reader = client.do_get(flight.Ticket(sql.encode("utf-8")))
    return reader.read_all()
