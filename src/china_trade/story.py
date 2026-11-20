"""Turn the gold tables into the figures and sentences the briefing uses."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from china_trade.catalog import DONORS, PRE_YEARS, RESTRICTED
from china_trade.graph import plain_partner
from china_trade.metrics import aud_text, pct_text, pct_text_1

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"

SHORT = {
    "988": "Confidential, not named",
    "278": "Other minerals",
    "285": "Alumina",
    "287": "Other metal ores",
    "289": "Precious-metal ores",
    **{code: meta["short"] for code, meta in RESTRICTED.items()},
    **DONORS,
}


def build_story(con: duckdb.DuckDBPyConnection) -> dict:
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    window = con.execute("SELECT start_period, end_period FROM silver.window").fetchone()
    latest = con.execute("SELECT * FROM gold.concentration_latest").fetchone()
    columns = [item[0] for item in con.execute("DESCRIBE gold.concentration_latest").fetchall()]
    latest_row = dict(zip(columns, latest, strict=True))
    share_series = con.execute(
        """
        SELECT year, china_share, china_aud, total_aud, hhi, top5_share, top_partner
        FROM gold.concentration_year
        WHERE complete
        ORDER BY year
        """
    ).fetchdf()
    commodities = con.execute(
        """
        SELECT sitc, abs_name, china_aud, world_aud, china_share_of_good, share_of_china
        FROM gold.commodity_latest
        ORDER BY china_aud DESC
        """
    ).fetchdf()
    partners = con.execute(
        """
        WITH buyers AS (
            SELECT m.country AS partner_code,
                   coalesce(cn.name, m.country) AS partner_name,
                   sum(m.aud) AS aud
            FROM silver.merch m
            LEFT JOIN silver.country_name cn ON cn.code = m.country
            , silver.window w
            WHERE m.commodity = 'TOT' AND m.state = 'TOT'
              AND m.period BETWEEN w.start_period AND w.end_period
              AND m.country NOT IN (
                  'TOT','APEC','ASEAN','DC','LDC','EURO27','EURO','OECD','JPDA','NCD','CNAV'
              )
            GROUP BY 1, 2
        ),
        official AS (
            SELECT sum(n.aud) AS total_aud
            FROM silver.national_month n, silver.window w
            WHERE n.period BETWEEN w.start_period AND w.end_period
        )
        SELECT partner_code, partner_name, aud, aud / total_aud AS share
        FROM buyers, official
        ORDER BY aud DESC
        """
    ).fetchdf()
    states = con.execute(
        """
        SELECT state_code, state_name, total_aud, china_aud, china_share, shock_aud
        FROM gold.state_shock
        ORDER BY shock_aud DESC
        """
    ).fetchdf()
    goods = _recovery(con)
    substitutes = con.execute(
        """
        SELECT sitc, plain, partner_code, partner_name, aud_2025, china_aud_2025, rank
        FROM gold.substitute
        ORDER BY sitc, rank
        """
    ).fetchdf()
    fx = con.execute(
        "SELECT year, aud_usd, aud_cny FROM gold.fx_year WHERE year >= 2010 ORDER BY year"
    ).fetchdf()
    revision = _revision(con)
    gas = con.execute(
        """
        SELECT world_aud FROM gold.commodity_year
        WHERE sitc = '343' AND year = 2025
        """
    ).fetchone()
    wheat = con.execute(
        """
        SELECT
            max(CASE WHEN year = 2019 THEN china_aud END),
            max(CASE WHEN year = 2023 THEN china_aud END)
        FROM gold.commodity_year
        WHERE sitc = '041'
        """
    ).fetchone()
    model = {
        row[0]: row
        for row in con.execute(
            """
            SELECT sitc, kind, pre_mape, lost_aud, lost_low, lost_high, weights_json, notes
            FROM gold.model_good
            """
        ).fetchall()
    }
    model_years = con.execute(
        "SELECT sitc, year, actual, prediction, low, high FROM gold.model_year ORDER BY sitc, year"
    ).fetchdf()

    y2006 = share_series[share_series["year"] == 2006].iloc[0]
    y2019 = share_series[share_series["year"] == 2019].iloc[0]
    y2022 = share_series[share_series["year"] == 2022].iloc[0]
    y2025 = share_series[share_series["year"] == 2025].iloc[0]
    iron_2025 = con.execute(
        """
        SELECT china_aud FROM gold.commodity_year WHERE sitc = '281' AND year = 2025
        """
    ).fetchone()[0]
    china_2025 = float(y2025["china_aud"])
    window_label = _month_span(window[0], window[1])
    exposure = _exposure(
        latest_row,
        share_series,
        commodities,
        partners,
        y2006,
        y2019,
        y2022,
        y2025,
        iron_2025,
        china_2025,
        window_label,
        gas[0] if gas else None,
    )
    recovery = _recovery_story(goods, model, model_years, wheat)
    state_story = _states(states, latest_row, window_label)
    grow = _grow(substitutes, con)
    fx_story = _fx(fx)
    return {
        "accessed": manifest["accessed_at_melbourne"],
        "window_label": window_label,
        "exposure": exposure,
        "recovery": recovery,
        "states": state_story,
        "grow": grow,
        "fx": fx_story,
        "revision": revision,
    }


def _exposure(
    latest,
    series,
    commodities,
    partners,
    y2006,
    y2019,
    y2022,
    y2025,
    iron_2025,
    china_2025,
    window_label,
    gas,
):
    named = []
    for row in commodities.itertuples(index=False):
        named.append(
            {
                "sitc": row.sitc,
                "label": _commodity_label(row.sitc, row.abs_name),
                "aud": float(row.china_aud),
                "share": float(row.share_of_china),
                "confidential": row.sitc == "988",
            }
        )
    top_partners = []
    for row in partners.head(6).itertuples(index=False):
        top_partners.append(
            {
                "code": row.partner_code,
                "label": plain_partner(row.partner_code, row.partner_name),
                "aud": float(row.aud),
                "share": float(row.share),
            }
        )
    history = [
        {
            "year": int(row.year),
            "share": float(row.china_share),
            "china_aud": float(row.china_aud),
            "total_aud": float(row.total_aud),
        }
        for row in series.itertuples(index=False)
    ]
    share = float(latest["china_share"])
    china_aud = float(latest["china_aud"])
    total_aud = float(latest["total_aud"])
    shock = china_aud * 0.10
    iron_share = float(iron_2025) / china_2025
    headline = (
        f"In the year to {_month_name(latest['end_period'])}, China bought "
        f"{pct_text_1(share)} of Australia's goods exports, {aud_text(china_aud)} "
        f"out of {aud_text(total_aud)}."
    )
    return {
        "headline": headline,
        "means": (
            f"China's share was {pct_text(float(y2006['china_share']))} in 2006 and "
            f"{pct_text_1(float(y2019['china_share']))} in 2019. It fell to "
            f"{pct_text_1(float(y2022['china_share']))} in 2022, when coal sales stopped, "
            f"and was {pct_text_1(float(y2025['china_share']))} in 2025. "
            f"A 10 percent fall in sales to China would put {aud_text(shock)} "
            f"of export income at stake in a year like the last one. "
            f"In 2025, iron ore alone was {aud_text(float(iron_2025))}, "
            f"{pct_text(iron_share)} of everything sold to China."
        ),
        "kpis": [
            {
                "label": "Share sold to China",
                "value": pct_text_1(share),
                "detail": window_label,
                "status": "part",
            },
            {
                "label": "Sales to China",
                "value": aud_text(china_aud),
                "detail": f"of {aud_text(total_aud)} in goods",
                "status": "part",
            },
            {
                "label": "Iron ore in 2025",
                "value": pct_text(iron_share),
                "detail": f"{aud_text(float(iron_2025))} of China sales",
                "status": "down",
            },
            {
                "label": "Five biggest buyers",
                "value": pct_text(float(latest["top5_share"])),
                "detail": "of all goods exports, latest year",
                "status": "part",
            },
            {
                "label": "If China sales fell 10%",
                "value": aud_text(shock),
                "detail": "export income at stake in one year",
                "status": "down",
            },
        ],
        "history": history,
        "commodities": named[:8],
        "partners": top_partners,
        "shock": shock,
        "gas_aud": None if gas is None else float(gas),
        "confidential_aud": next(item["aud"] for item in named if item["sitc"] == "988"),
    }


def _recovery(con: duckdb.DuckDBPyConnection) -> list[dict]:
    frame = con.execute(
        """
        SELECT sitc, plain, year, aud, months_unpublished, complete
        FROM gold.china_goods_year
        ORDER BY sitc, year
        """
    ).fetchdf()
    months = con.execute(
        """
        SELECT sitc, period, aud FROM gold.restricted_month
        WHERE year >= 2018
        ORDER BY sitc, period
        """
    ).fetchdf()
    goods = []
    for sitc, meta in RESTRICTED.items():
        rows = frame[frame["sitc"] == sitc]
        pre = rows[rows["year"].isin(PRE_YEARS)]["aud"].mean()
        during_years = [year for year in range(meta["treat"], meta["lift"])]
        during = rows[rows["year"].isin(during_years)]["aud"].mean()
        y2025 = float(rows[rows["year"] == 2025]["aud"].iloc[0])
        y2026 = rows[rows["year"] == 2026]
        ytd = float(y2026["aud"].iloc[0]) if len(y2026) else 0.0
        ytd_months = int(12 - y2026["months_unpublished"].iloc[0]) if len(y2026) else 0
        # months_unpublished counts filled zeros, not "months present".
        # 2026 has 9 real or filled months in the scaffold through September.
        ytd_months = int(
            months[(months["sitc"] == sitc) & (months["period"].dt.year == 2026)].shape[0]
        )
        ratio = y2025 / pre if pre else 0.0
        goods.append(
            {
                "sitc": sitc,
                "plain": meta["plain"],
                "short": meta["short"],
                "note": meta["note"],
                "treat": meta["treat"],
                "lift": meta["lift"],
                "pre": float(pre),
                "during": float(during),
                "y2025": y2025,
                "ytd": ytd,
                "ytd_months": ytd_months,
                "ratio": float(ratio),
                "status": _status(ratio),
                "annual": [
                    {"year": int(row.year), "aud": float(row.aud)}
                    for row in rows.itertuples(index=False)
                    if 2017 <= row.year <= 2025
                ],
                "monthly": [
                    {"period": row.period.strftime("%Y-%m"), "aud": float(row.aud)}
                    for row in months[months["sitc"] == sitc].itertuples(index=False)
                ],
            }
        )
    return goods


def _recovery_story(goods, model, model_years, wheat) -> dict:
    for good in goods:
        fitted = model.get(good["sitc"])
        good["lost"] = None if fitted is None else float(fitted[3])
        good["lost_low"] = None if fitted is None else float(fitted[4])
        good["lost_high"] = None if fitted is None else float(fitted[5])
        good["pre_mape"] = None if fitted is None else float(fitted[2])
        good["weights"] = {} if fitted is None else json.loads(fitted[6])
        good["model_note"] = "" if fitted is None else fitted[7]
        years = model_years[model_years["sitc"] == good["sitc"]]
        by_year = {int(row.year): row for row in years.itertuples(index=False)}
        for point in good["annual"]:
            fit = by_year.get(point["year"])
            if fit is None or point["year"] < good["treat"]:
                point["prediction"] = None
                point["low"] = None
                point["high"] = None
            else:
                point["prediction"] = float(fit.prediction)
                point["low"] = float(fit.low)
                point["high"] = float(fit.high)
    back = [good for good in goods if good["status"] == "back"]
    part = [good for good in goods if good["status"] == "part"]
    down = [good for good in goods if good["status"] == "down"]
    for good in goods:
        good["recorded_gap"] = _recorded_gap(good)
    shortfall_total = sum(good["recorded_gap"] for good in goods)
    biggest = max(goods, key=lambda good: good["recorded_gap"])

    def names(rows):
        return _join(good["short"] for good in rows)

    headline = (
        f"By 2025, {_count_word(len(back))} of the eight blocked groups were back to at least "
        f"90 percent of their 2017–19 sales to China"
        + (f" ({names(back)})" if back else "")
        + ". "
        + (f"{names(part)} were only part of the way back. " if part else "")
        + (f"{names(down)} were still well short." if down else "None were still well short.")
    )
    means = (
        "“Back” means 2025 sales reached at least 90 percent of the 2017–19 average. "
        f"During the blocked years, recorded sales across all eight blocked groups were "
        f"{aud_text(shortfall_total)} below that old average. {biggest['short']} is most of it, "
        f"about {aud_text(biggest['recorded_gap'])}. "
        "A comparison with goods that were not blocked is in the method note. "
        "It also moves for wool, which was not blocked, so these pages use the recorded average."
    )
    wheat_sentence = ""
    if wheat and wheat[0] and wheat[1]:
        wheat_sentence = (
            f"China's wheat purchases rose from {aud_text(float(wheat[0]))} in 2019 to "
            f"{aud_text(float(wheat[1]))} in 2023, while barley was blocked. "
            "Wheat is not used as a stand-in for a normal year."
        )
    placebo = model.get("268")
    return {
        "headline": headline,
        "means": means,
        "wheat": wheat_sentence,
        "goods": goods,
        "back": [good["short"] for good in back],
        "part": [good["short"] for good in part],
        "down": [good["short"] for good in down],
        "shortfall_total": shortfall_total,
        "placebo": None
        if placebo is None
        else {
            "lost": float(placebo[3]),
            "lost_low": float(placebo[4]),
            "lost_high": float(placebo[5]),
            "pre_mape": float(placebo[2]),
        },
    }


def _states(states, latest, window_label) -> dict:
    national_shock = float(latest["china_aud"]) * 0.10
    rows = []
    for row in states.itertuples(index=False):
        rows.append(
            {
                "code": row.state_code,
                "name": row.state_name,
                "total": float(row.total_aud),
                "china": float(row.china_aud),
                "share": 0.0 if row.china_share is None else float(row.china_share),
                "shock": float(row.shock_aud),
            }
        )
    wa = next(row for row in rows if row["name"] == "Western Australia")
    tas = next(row for row in rows if row["name"] == "Tasmania")
    headline = (
        f"A 10 percent fall in sales to China would put {aud_text(wa['shock'])} "
        f"at stake in Western Australia, {pct_text(wa['shock'] / national_shock)} "
        f"of the national {aud_text(national_shock)}."
    )
    means = (
        f"Western Australia sent {pct_text_1(wa['share'])} of its goods exports to China "
        f"in {window_label}. Tasmania's share was {pct_text(tas['share'])}, "
        f"but the income at stake there is {aud_text(tas['shock'])}. "
        "The map shows the share. The bars show the dollars."
    )
    return {
        "headline": headline,
        "means": means,
        "rows": rows,
        "national_shock": national_shock,
        "window_label": window_label,
        "kpis": [
            {
                "label": "Western Australia at stake",
                "value": aud_text(wa["shock"]),
                "detail": "if China sales fall by a tenth",
                "status": "down",
            },
            {
                "label": "WA share of the national hit",
                "value": pct_text(wa["shock"] / national_shock),
                "detail": f"of {aud_text(national_shock)}",
                "status": "down",
            },
            {
                "label": "WA reliance on China",
                "value": pct_text_1(wa["share"]),
                "detail": "of the state's goods exports",
                "status": "down",
            },
            {
                "label": "Tasmania at stake",
                "value": aud_text(tas["shock"]),
                "detail": f"{pct_text(tas['share'])} of state exports, small dollars",
                "status": "part",
            },
        ],
    }


def _grow(substitutes, con: duckdb.DuckDBPyConnection) -> dict:
    focus = ["321", "281", "112", "247", "011", "043", "036", "263", "283"]
    cards = []
    for sitc in focus:
        rows = substitutes[substitutes["sitc"] == sitc].sort_values("rank")
        if rows.empty:
            continue
        china = float(rows.iloc[0]["china_aud_2025"])
        plain = rows.iloc[0]["plain"]
        buyers = []
        buyers.append({"label": "China", "aud": china, "code": "CHIN"})
        for row in rows.head(5).itertuples(index=False):
            buyers.append(
                {
                    "label": plain_partner(row.partner_code, row.partner_name),
                    "aud": float(row.aud_2025),
                    "code": row.partner_code,
                }
            )
        nxt = buyers[1]
        cards.append(
            {
                "sitc": sitc,
                "plain": plain,
                "china": china,
                "next_label": nxt["label"],
                "next_aud": nxt["aud"],
                "ratio": nxt["aud"] / china if china else 0.0,
                "serious": nxt["aud"] >= 0.5 * china and china > 0,
                "buyers": buyers,
            }
        )
    serious = [card for card in cards if card["serious"] and card["sitc"] != "281"]
    thin = [card for card in cards if not card["serious"]]
    headline = (
        f"{_join(card['plain'] for card in serious)} already "
        f"{'have' if len(serious) != 1 else 'has'} another buyer at least half as large as China. "
        f"{_join(card['plain'] for card in thin)} "
        f"{'do' if len(thin) != 1 else 'does'} not."
    )
    iron = next(card for card in cards if card["sitc"] == "281")
    means = (
        f"In 2025 {iron['next_label']} bought {aud_text(iron['next_aud'])} of Australian iron ore. "
        f"China bought {aud_text(iron['china'])}. "
        "Trade promotion can deepen a market that already exists. "
        "It cannot replace iron ore sales to China in the next few years."
    )
    return {
        "headline": headline,
        "means": means,
        "cards": cards,
        "default": "321",
        "kpis": [
            {
                "label": "Iron ore's next buyer",
                "value": pct_text(iron["ratio"]),
                "detail": f"{iron['next_label']}, against China",
                "status": "down",
            },
            {
                "label": "Goods with a real second buyer",
                "value": str(len(serious)),
                "detail": "at least half of China's 2025 purchases",
                "status": "back",
            },
            {
                "label": "Goods without one",
                "value": str(len(thin)),
                "detail": _join(card["plain"] for card in thin),
                "status": "part",
            },
            {
                "label": "Coal's largest other buyer",
                "value": aud_text(
                    next(card["next_aud"] for card in cards if card["sitc"] == "321")
                ),
                "detail": next(card["next_label"] for card in cards if card["sitc"] == "321"),
                "status": "back",
            },
        ],
    }


def _fx(fx) -> dict:
    y2019 = fx[fx["year"] == 2019].iloc[0]
    y2025 = fx[fx["year"] == 2025].iloc[0]
    latest = fx.iloc[-1]
    change = float(y2025["aud_usd"]) / float(y2019["aud_usd"]) - 1
    direction = "weaker" if change < 0 else "stronger"
    sentence = (
        f"The Australian dollar bought {float(y2019['aud_usd']):.2f} US dollars on average in 2019 "
        f"and {float(y2025['aud_usd']):.2f} in 2025, so it was {abs(change) * 100:.0f} percent {direction}. "
        f"On the latest published day it bought {float(latest['aud_usd']):.2f} US dollars "
        f"and {float(latest['aud_cny']):.2f} yuan. "
        "Export income on these pages is in Australian dollars, the way the ABS publishes it."
    )
    return {
        "sentence": sentence,
        "series": [
            {"year": int(row.year), "usd": float(row.aud_usd), "cny": float(row.aud_cny)}
            for row in fx.itertuples(index=False)
            if int(row.year) <= 2025
        ],
    }


def _revision(con: duckdb.DuckDBPyConnection) -> dict:
    summary = con.execute(
        """
        SELECT
            count(*) FILTER (
                WHERE abs(revision_million) >= 0.5 AND country_name NOT LIKE 'Total%'
            ) AS cells,
            coalesce(sum(abs(revision_million)) FILTER (
                WHERE abs(revision_million) >= 0.5 AND country_name NOT LIKE 'Total%'
            ), 0) AS abs_million
        FROM gold.revision_cell
        WHERE older_million IS NOT NULL
        """
    ).fetchone()
    china = con.execute(
        """
        SELECT period, older_million, newer_million, revision_million
        FROM gold.revision_cell
        WHERE country_name LIKE 'China (excludes%'
        ORDER BY period
        """
    ).fetchall()
    total = con.execute(
        """
        SELECT period, revision_million
        FROM gold.revision_cell
        WHERE country_name LIKE 'Total (%'
          AND older_million IS NOT NULL
          AND abs(revision_million) >= 0.5
        ORDER BY period
        """
    ).fetchall()
    china_changes = [
        {
            "period": row[0].isoformat(),
            "older": None if row[1] is None else float(row[1]),
            "newer": None if row[2] is None else float(row[2]),
            "revision": None if row[3] is None else float(row[3]),
        }
        for row in china
        if row[3] is None or abs(row[3]) >= 0.5
    ]
    return {
        "cells": int(summary[0]),
        "abs_aud": float(summary[1]) * 1_000_000,
        "china": china_changes,
        "total_changes": [
            {"period": row[0].isoformat(), "revision_million": float(row[1])} for row in total
        ],
    }


def _commodity_label(sitc: str, abs_name: str) -> str:
    if sitc in SHORT:
        return SHORT[sitc]
    name = abs_name.split("(")[0].strip()
    if len(name) > 42:
        name = name[:40].rstrip() + "…"
    return name


def _recorded_gap(good: dict) -> float:
    total = 0.0
    for point in good["annual"]:
        if good["treat"] <= point["year"] < good["lift"] and point["aud"] < good["pre"]:
            total += good["pre"] - point["aud"]
    return total


def _status(ratio: float) -> str:
    if ratio >= 0.9:
        return "back"
    if ratio >= 0.4:
        return "part"
    return "down"


def _count_word(value: int) -> str:
    words = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight"]
    return words[value] if value < len(words) else str(value)


def _join(items) -> str:
    values = list(items)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


def _month_name(value) -> str:
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{months[value.month - 1]} {value.year}"


def _month_span(start, end) -> str:
    return f"{_month_name(start)} to {_month_name(end)}"
