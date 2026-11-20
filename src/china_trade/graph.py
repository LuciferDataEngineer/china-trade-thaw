"""Who else already buys each China-exposed good.

DuckPGQ is the property-graph extension this project asks for. DuckDB 2.0.1
returns HTTP 404 for that extension on linux_amd64, from both the core and the
community repositories. The walk below is the fallback: a recursive query that
starts at China, steps to each good China buys, then steps to every other
buyer of that good.
"""

from __future__ import annotations

import duckdb

from china_trade.catalog import DONORS, MARKET_FLOOR_AUD, PARTNER_PLAIN, RESTRICTED


def build_graph(con: duckdb.DuckDBPyConnection) -> dict:
    plain = {**{code: meta["plain"] for code, meta in RESTRICTED.items()}, **DONORS}
    values = ", ".join(f"('{code}', '{name}')" for code, name in plain.items())
    con.execute(
        f"""
        DROP TABLE IF EXISTS silver.good_plain;
        DROP TABLE IF EXISTS gold.substitute;
        CREATE TABLE silver.good_plain (sitc VARCHAR, plain VARCHAR);
        INSERT INTO silver.good_plain VALUES {values};

        CREATE TABLE gold.substitute AS
        WITH RECURSIVE walk AS (
            SELECT
                'partner' AS kind,
                'CHIN' AS node,
                0 AS depth,
                CAST(NULL AS VARCHAR) AS sitc,
                0.0::DOUBLE AS aud
            UNION ALL
            SELECT
                CASE WHEN w.depth = 0 THEN 'commodity' ELSE 'partner' END,
                CASE WHEN w.depth = 0 THEN e.sitc ELSE e.partner_code END,
                w.depth + 1,
                CASE WHEN w.depth = 0 THEN e.sitc ELSE w.sitc END,
                e.aud::DOUBLE
            FROM walk w
            JOIN gold.edge_2025 e
              ON (
                    (w.depth = 0 AND e.partner_code = w.node)
                 OR (w.depth = 1 AND e.sitc = w.sitc AND e.partner_code <> 'CHIN')
              )
            WHERE w.depth < 2
        )
        SELECT
            w.sitc,
            p.plain,
            w.node AS partner_code,
            e.partner_name,
            w.aud AS aud_2025,
            china.aud AS china_aud_2025,
            row_number() OVER (PARTITION BY w.sitc ORDER BY w.aud DESC) AS rank,
            w.aud >= {MARKET_FLOOR_AUD} AS real_market
        FROM walk w
        JOIN silver.good_plain p ON p.sitc = w.sitc
        JOIN gold.edge_2025 e ON e.sitc = w.sitc AND e.partner_code = w.node
        JOIN gold.edge_2025 china ON china.sitc = w.sitc AND china.partner_code = 'CHIN'
        WHERE w.depth = 2
        """
    )
    duckpgq_error = _try_duckpgq(con)
    rows = con.execute("SELECT count(*) FROM gold.substitute").fetchone()[0]
    if rows < 8:
        raise AssertionError(f"substitute paths look empty: {rows}")
    return {
        "engine": "recursive-sql",
        "duckpgq_error": duckpgq_error,
        "paths": int(rows),
        "floor_aud": MARKET_FLOOR_AUD,
    }


def plain_partner(code: str, abs_name: str) -> str:
    if code in PARTNER_PLAIN:
        return PARTNER_PLAIN[code]
    name = abs_name.split("(")[0].strip(" ;")
    return name or code


def _try_duckpgq(con: duckdb.DuckDBPyConnection) -> str:
    try:
        con.execute("INSTALL duckpgq")
        con.execute("LOAD duckpgq")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}".split("\n")[0][:500]
    con.execute(
        """
        CREATE PROPERTY GRAPH trade_graph
        VERTEX TABLES (
            silver.good_plain
        )
        """
    )
    return ""
