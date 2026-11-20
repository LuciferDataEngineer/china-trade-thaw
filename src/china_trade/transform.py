"""Bronze files to silver and gold tables in DuckDB.

Missing months for the blocked China series are filled with zero. ABS does not
publish a zero, and those gaps line up with the years the restrictions were in
force. Other series keep only the months ABS published.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from china_trade.catalog import (
    DONORS,
    EXCLUDED_MARKETS,
    RESTRICTED,
    STATE_NAMES,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
GOLD_DB = ROOT / "data" / "warehouse.duckdb"

EXCLUDED = sorted(EXCLUDED_MARKETS | {"NCD", "CNAV"})


def connect(path: Path = GOLD_DB) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    wal = path.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()
    return duckdb.connect(str(path))


def build_descriptive(con: duckdb.DuckDBPyConnection, snapshot: Path = SNAPSHOT) -> None:
    merch = (snapshot / "merch_month.parquet").as_posix()
    labels = (snapshot / "labels.parquet").as_posix()
    vintage = (snapshot / "country_vintage.parquet").as_posix()
    fx = (snapshot / "fx_daily.parquet").as_posix()
    excluded = ", ".join(f"'{code}'" for code in EXCLUDED)
    restricted_values = ", ".join(
        f"('{code}', '{meta['plain']}', {meta['treat']}, {meta['lift']})"
        for code, meta in RESTRICTED.items()
    )
    donor_list = ", ".join(f"'{code}'" for code in DONORS)
    state_values = ", ".join(f"('{code}', '{name}')" for code, name in STATE_NAMES.items())

    con.execute(
        f"""
        CREATE SCHEMA IF NOT EXISTS silver;
        CREATE SCHEMA IF NOT EXISTS gold;

        CREATE TABLE silver.merch AS
        SELECT
            commodity,
            country,
            state,
            period,
            year(period) AS year,
            month(period) AS month,
            aud,
            obs_status
        FROM read_parquet('{merch}')
        WHERE aud IS NOT NULL AND aud >= 0;

        CREATE TABLE silver.country_name AS
        SELECT code, name FROM read_parquet('{labels}') WHERE dimension = 'country';

        CREATE TABLE silver.commodity_name AS
        SELECT code, name FROM read_parquet('{labels}') WHERE dimension = 'commodity';

        CREATE TABLE silver.national_month AS
        SELECT period, year, aud
        FROM silver.merch
        WHERE commodity = 'TOT' AND country = 'TOT' AND state = 'TOT';

        CREATE TABLE silver.window AS
        SELECT
            (max(period) - INTERVAL 11 MONTH)::DATE AS start_period,
            max(period) AS end_period
        FROM silver.national_month;

        CREATE TABLE silver.restricted_good (
            sitc VARCHAR, plain VARCHAR, treat_year INTEGER, lift_year INTEGER
        );
        INSERT INTO silver.restricted_good VALUES {restricted_values};

        CREATE TABLE silver.state (code VARCHAR, name VARCHAR);
        INSERT INTO silver.state VALUES {state_values};

        CREATE TABLE gold.restricted_month AS
        WITH cal AS (
            SELECT generate_series::DATE AS period
            FROM generate_series(
                DATE '2006-01-01',
                (SELECT max(period) FROM silver.national_month),
                INTERVAL 1 MONTH
            )
        )
        SELECT
            g.sitc,
            g.plain,
            c.period,
            year(c.period) AS year,
            coalesce(m.aud, 0) AS aud,
            m.aud IS NULL AS filled_zero
        FROM cal c
        CROSS JOIN silver.restricted_good g
        LEFT JOIN silver.merch m
            ON m.commodity = g.sitc
           AND m.country = 'CHIN'
           AND m.state = 'TOT'
           AND m.period = c.period;

        CREATE TABLE gold.china_goods_year AS
        SELECT
            sitc,
            plain,
            year,
            sum(aud) AS aud,
            sum(CASE WHEN filled_zero THEN 1 ELSE 0 END) AS months_unpublished,
            count(*) = 12 AS complete
        FROM gold.restricted_month
        GROUP BY sitc, plain, year;

        CREATE TABLE gold.donor_year AS
        SELECT commodity AS sitc, year, sum(aud) AS aud, count(*) AS months
        FROM silver.merch
        WHERE country = 'CHIN' AND state = 'TOT' AND commodity IN ({donor_list})
        GROUP BY commodity, year;

        CREATE TABLE gold.partner_year AS
        WITH buyers AS (
            SELECT year, country, sum(aud) AS aud
            FROM silver.merch
            WHERE commodity = 'TOT' AND state = 'TOT' AND country NOT IN ({excluded})
            GROUP BY year, country
        ),
        official AS (
            SELECT year, sum(aud) AS aud
            FROM silver.national_month
            GROUP BY year
        )
        SELECT
            b.year,
            (SELECT count(*) = 12 FROM silver.national_month n WHERE n.year = b.year) AS complete,
            b.country AS partner_code,
            coalesce(cn.name, b.country) AS partner_name,
            b.aud,
            b.aud / o.aud AS share
        FROM buyers b
        JOIN official o USING (year)
        LEFT JOIN silver.country_name cn ON cn.code = b.country;

        CREATE TABLE gold.concentration_year AS
        WITH ranked AS (
            SELECT
                year,
                complete,
                aud,
                share,
                partner_name,
                aud / sum(aud) OVER (PARTITION BY year) AS hhi_share,
                row_number() OVER (PARTITION BY year ORDER BY aud DESC) AS rk
            FROM gold.partner_year
        ),
        china AS (
            SELECT year, aud, share
            FROM gold.partner_year
            WHERE partner_code = 'CHIN'
        ),
        official AS (
            SELECT year, sum(aud) AS aud, count(*) = 12 AS complete
            FROM silver.national_month
            GROUP BY year
        )
        SELECT
            r.year,
            o.complete,
            o.aud AS total_aud,
            c.aud AS china_aud,
            c.share AS china_share,
            max(CASE WHEN r.rk = 1 THEN r.partner_name END) AS top_partner,
            max(CASE WHEN r.rk = 1 THEN r.share END) AS top_share,
            sum(CASE WHEN r.rk <= 5 THEN r.share ELSE 0 END) AS top5_share,
            sum(power(r.hhi_share, 2)) AS hhi,
            count(*) AS partner_count
        FROM ranked r
        JOIN official o USING (year)
        JOIN china c USING (year)
        GROUP BY r.year, o.complete, o.aud, c.aud, c.share;

        CREATE TABLE gold.concentration_latest AS
        WITH buyers AS (
            SELECT country, sum(m.aud) AS aud
            FROM silver.merch m, silver.window w
            WHERE m.commodity = 'TOT' AND m.state = 'TOT'
              AND m.country NOT IN ({excluded})
              AND m.period BETWEEN w.start_period AND w.end_period
            GROUP BY country
        ),
        official AS (
            SELECT sum(n.aud) AS aud
            FROM silver.national_month n, silver.window w
            WHERE n.period BETWEEN w.start_period AND w.end_period
        ),
        ranked AS (
            SELECT
                b.country,
                coalesce(cn.name, b.country) AS partner_name,
                b.aud,
                b.aud / o.aud AS share,
                b.aud / sum(b.aud) OVER () AS hhi_share,
                row_number() OVER (ORDER BY b.aud DESC) AS rk
            FROM buyers b
            CROSS JOIN official o
            LEFT JOIN silver.country_name cn ON cn.code = b.country
        )
        SELECT
            (SELECT start_period FROM silver.window) AS start_period,
            (SELECT end_period FROM silver.window) AS end_period,
            (SELECT aud FROM official) AS total_aud,
            max(CASE WHEN country = 'CHIN' THEN aud END) AS china_aud,
            max(CASE WHEN country = 'CHIN' THEN share END) AS china_share,
            max(CASE WHEN rk = 1 THEN partner_name END) AS top_partner,
            max(CASE WHEN rk = 1 THEN share END) AS top_share,
            sum(CASE WHEN rk <= 5 THEN share ELSE 0 END) AS top5_share,
            sum(power(hhi_share, 2)) AS hhi
        FROM ranked;

        CREATE TABLE gold.commodity_latest AS
        WITH china AS (
            SELECT m.commodity, sum(m.aud) AS aud
            FROM silver.merch m, silver.window w
            WHERE m.country = 'CHIN' AND m.state = 'TOT'
              AND regexp_matches(m.commodity, '^[0-9]{{3}}$')
              AND m.period BETWEEN w.start_period AND w.end_period
            GROUP BY m.commodity
        ),
        world AS (
            SELECT m.commodity, sum(m.aud) AS aud
            FROM silver.merch m, silver.window w
            WHERE m.country = 'TOT' AND m.state = 'TOT'
              AND regexp_matches(m.commodity, '^[0-9]{{3}}$')
              AND m.period BETWEEN w.start_period AND w.end_period
            GROUP BY m.commodity
        ),
        china_total AS (
            SELECT sum(m.aud) AS aud
            FROM silver.merch m, silver.window w
            WHERE m.commodity = 'TOT' AND m.country = 'CHIN' AND m.state = 'TOT'
              AND m.period BETWEEN w.start_period AND w.end_period
        )
        SELECT
            c.commodity AS sitc,
            coalesce(n.name, c.commodity) AS abs_name,
            c.aud AS china_aud,
            w.aud AS world_aud,
            c.aud / nullif(w.aud, 0) AS china_share_of_good,
            c.aud / t.aud AS share_of_china
        FROM china c
        LEFT JOIN world w USING (commodity)
        LEFT JOIN silver.commodity_name n ON n.code = c.commodity
        CROSS JOIN china_total t;

        CREATE TABLE gold.commodity_year AS
        SELECT
            m.year,
            m.commodity AS sitc,
            sum(m.aud) FILTER (WHERE m.country = 'CHIN') AS china_aud,
            sum(m.aud) FILTER (WHERE m.country = 'TOT') AS world_aud
        FROM silver.merch m
        WHERE m.state = 'TOT'
          AND m.country IN ('CHIN', 'TOT')
          AND regexp_matches(m.commodity, '^[0-9]{{3}}$')
        GROUP BY m.year, m.commodity;

        CREATE TABLE gold.state_shock AS
        WITH flows AS (
            SELECT m.state, m.country, sum(m.aud) AS aud
            FROM silver.merch m, silver.window w
            WHERE m.commodity = 'TOT'
              AND m.state IN (SELECT code FROM silver.state)
              AND m.country IN ('CHIN', 'TOT')
              AND m.period BETWEEN w.start_period AND w.end_period
            GROUP BY m.state, m.country
        )
        SELECT
            s.code AS state_code,
            s.name AS state_name,
            coalesce(max(f.aud) FILTER (WHERE f.country = 'TOT'), 0) AS total_aud,
            coalesce(max(f.aud) FILTER (WHERE f.country = 'CHIN'), 0) AS china_aud,
            coalesce(max(f.aud) FILTER (WHERE f.country = 'CHIN'), 0)
                / nullif(max(f.aud) FILTER (WHERE f.country = 'TOT'), 0) AS china_share,
            0.10 * coalesce(max(f.aud) FILTER (WHERE f.country = 'CHIN'), 0) AS shock_aud,
            (SELECT start_period FROM silver.window) AS window_start,
            (SELECT end_period FROM silver.window) AS window_end
        FROM silver.state s
        LEFT JOIN flows f ON f.state = s.code
        GROUP BY s.code, s.name;

        CREATE TABLE gold.state_commodity AS
        SELECT
            m.state AS state_code,
            m.commodity AS sitc,
            sum(m.aud) AS china_aud
        FROM silver.merch m, silver.window w
        WHERE m.country = 'CHIN'
          AND m.state IN (SELECT code FROM silver.state)
          AND (
                m.commodity IN (SELECT sitc FROM silver.restricted_good)
                OR m.commodity IN ({donor_list})
              )
          AND m.period BETWEEN w.start_period AND w.end_period
        GROUP BY m.state, m.commodity;

        CREATE TABLE gold.edge_2025 AS
        SELECT
            m.commodity AS sitc,
            m.country AS partner_code,
            coalesce(cn.name, m.country) AS partner_name,
            sum(m.aud) AS aud
        FROM silver.merch m
        LEFT JOIN silver.country_name cn ON cn.code = m.country
        WHERE m.state = 'TOT'
          AND m.year = 2025
          AND m.country NOT IN ({excluded})
          AND (
                m.commodity IN (SELECT sitc FROM silver.restricted_good)
                OR m.commodity IN ({donor_list})
              )
        GROUP BY m.commodity, m.country, cn.name
        HAVING sum(m.aud) > 0;

        CREATE TABLE gold.fx_year AS
        SELECT
            year(CAST(date AS DATE)) AS year,
            avg(aud_usd) AS aud_usd,
            avg(aud_cny) AS aud_cny
        FROM read_parquet('{fx}')
        WHERE aud_usd IS NOT NULL
        GROUP BY year(CAST(date AS DATE));

        CREATE TABLE gold.revision_cell AS
        SELECT
            country_name,
            CAST(period AS DATE) AS period,
            max(aud_million) FILTER (WHERE vintage = '2026-08') AS older_million,
            max(aud_million) FILTER (WHERE vintage = '2026-09') AS newer_million,
            max(aud_million) FILTER (WHERE vintage = '2026-09')
                - max(aud_million) FILTER (WHERE vintage = '2026-08') AS revision_million
        FROM read_parquet('{vintage}')
        GROUP BY country_name, period;

        CREATE TABLE gold.crosscheck AS
        SELECT
            'CHIN' AS partner_code,
            DATE '2026-09-01' AS period,
            (SELECT aud FROM silver.merch
             WHERE commodity = 'TOT' AND country = 'CHIN' AND state = 'TOT'
               AND period = DATE '2026-09-01') AS api_aud,
            (SELECT newer_million * 1000000 FROM gold.revision_cell
             WHERE country_name LIKE 'China (excludes%'
               AND period = DATE '2026-09-01') AS workbook_aud;
        """
    )


def assert_descriptive(con: duckdb.DuckDBPyConnection) -> None:
    """Stop the build if the extract does not describe the trade restrictions."""
    china_2025 = con.execute(
        """
        SELECT china_share FROM gold.concentration_year
        WHERE year = 2025 AND complete
        """
    ).fetchone()
    if china_2025 is None or not 0.25 <= china_2025[0] <= 0.45:
        raise AssertionError(f"2025 China share out of range: {china_2025}")

    bans = con.execute(
        """
        SELECT sitc, aud FROM gold.china_goods_year
        WHERE year = 2021 AND sitc IN ('321', '112', '043')
        """
    ).fetchall()
    found = {sitc: aud for sitc, aud in bans}
    if found.get("321", 1e12) > 500_000_000:
        raise AssertionError(f"coal 2021 should show the stoppage, got {found}")
    if found.get("112", 1e12) > 200_000_000:
        raise AssertionError(f"wine 2021 should show the stoppage, got {found}")
    if found.get("043", 1) != 0:
        raise AssertionError(f"barley 2021 should have no recorded sales, got {found}")

    shock = con.execute(
        """
        SELECT abs(shock_aud - 0.10 * china_aud) < 1
        FROM gold.state_shock
        """
    ).fetchall()
    if not shock or not all(row[0] for row in shock):
        raise AssertionError("state shock is not 10 percent of China sales")

    gap = con.execute(
        """
        SELECT abs(api_aud - workbook_aud) < 1000000
        FROM gold.crosscheck
        """
    ).fetchone()
    if gap is None or not gap[0]:
        raise AssertionError(f"API and September workbook disagree on China: {gap}")

    unchanged = con.execute(
        """
        SELECT count(*) FROM gold.revision_cell
        WHERE country_name LIKE 'China (excludes%'
          AND period < DATE '2026-03-01'
          AND older_million IS NOT NULL
          AND abs(revision_million) >= 0.5
        """
    ).fetchone()[0]
    if unchanged != 0:
        raise AssertionError("China months before March 2026 were revised")
