"""Checks between the silver extract and the gold tables."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandera.pandas as pa
from pandera.typing import Series

ROOT = Path(__file__).resolve().parents[2]


class StateShock(pa.DataFrameModel):
    state_code: Series[str]
    state_name: Series[str]
    total_aud: Series[float] = pa.Field(ge=0)
    china_aud: Series[float] = pa.Field(ge=0)
    shock_aud: Series[float] = pa.Field(ge=0)

    class Config:
        strict = False
        coerce = True


def check_frames(con) -> None:
    frame = con.execute(
        """
        SELECT state_code, state_name, total_aud, china_aud, china_share, shock_aud
        FROM gold.state_shock
        """
    ).fetchdf()
    StateShock.validate(frame)
    bad = con.execute(
        """
        SELECT count(*) FROM gold.concentration_year
        WHERE china_share < 0 OR china_share > 1 OR hhi < 0 OR hhi > 1 OR top5_share > 1.001
        """
    ).fetchone()[0]
    if bad:
        raise AssertionError(f"{bad} concentration rows are outside 0 to 1")
    order = con.execute(
        """
        SELECT year FROM gold.concentration_year WHERE complete ORDER BY year
        """
    ).fetchall()
    years = [row[0] for row in order]
    if years != sorted(years):
        raise AssertionError("years are not chronological")


def check_contract(con) -> None:
    """Lint the Open Data Contract and run its SQL rules in-process.

    ``datacontract test`` links a DuckDB extra that pins DuckDB 1.5. DuckLake
    here uses DuckDB 2.0.1, and that CLI still calls ``fetch_arrow_table``,
    which DuckDB 2 removed. The lint checks the contract document. The SQL
    rules in the contract are executed directly.
    """
    contract = ROOT / "contracts" / "gold-exposure.odcs.yaml"
    cli = str(Path(sys.executable).with_name("datacontract"))
    lint = subprocess.run(
        [cli, "lint", str(contract)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if lint.returncode != 0:
        raise AssertionError(lint.stdout + lint.stderr)
    checks = [
        (
            "shock is one tenth",
            "SELECT count(*) FROM gold.state_shock WHERE abs(shock_aud - 0.10 * china_aud) > 1",
            0,
        ),
        ("eight states", "SELECT count(*) FROM gold.state_shock", 8),
        (
            "shares in range",
            """
                SELECT count(*) FROM gold.concentration_year
                WHERE china_share < 0 OR china_share > 1 OR hhi < 0 OR hhi > 1
                """,
            0,
        ),
        (
            "2025 china share",
            """
                SELECT count(*) FROM gold.concentration_year
                WHERE year = 2025 AND complete AND china_share BETWEEN 0.25 AND 0.45
                """,
            1,
        ),
    ]
    for label, sql, expected in checks:
        got = con.execute(sql).fetchone()[0]
        if got != expected:
            raise AssertionError(f"{label}: expected {expected}, got {got}")
