"""Method note. The briefing pages do not use these terms."""

from __future__ import annotations

from pathlib import Path

from china_trade.metrics import aud_text, pct_text, pct_text_1

ROOT = Path(__file__).resolve().parents[2]


def write(story: dict, graph: dict) -> None:
    revision = story["revision"]
    china_lines = []
    for row in revision["china"]:
        if row["revision"] is None:
            china_lines.append(
                f"| {row['period'][:7]} | new month | {row['newer']:.0f} | added in the September release |"
            )
        else:
            china_lines.append(
                f"| {row['period'][:7]} | {row['older']:.0f} | {row['newer']:.0f} | {row['revision']:+.0f} |"
            )
    total_lines = [
        f"| {row['period'][:7]} | {row['revision_million']:+.0f} |"
        for row in revision["total_changes"]
    ]
    goods = story["recovery"]["goods"]
    model_lines = []
    for good in goods:
        if good["lost"] is None:
            continue
        weights = ", ".join(
            f"{name} {weight * 100:.0f}%" for name, weight in good["weights"].items()
        )
        model_lines.append(
            f"| {good['short']} | {good['treat']}–{good['lift'] - 1} | "
            f"{good['lost'] / 1e6:.0f} | {good['lost_low'] / 1e6:.0f} to {good['lost_high'] / 1e6:.0f} | "
            f"{good['pre_mape'] * 100:.0f}% | {weights} |"
        )
    placebo = story["recovery"]["placebo"]
    placebo_line = "The wool check did not run."
    if placebo is not None:
        placebo_line = (
            f"Wool, which was not blocked, was put through the same comparison as if a restriction "
            f"had started in 2020 and lasted through 2022. The central gap is {aud_text(placebo['lost'])} "
            f"(likely range {aud_text(placebo['lost_low'])} to {aud_text(placebo['lost_high'])}). "
            "A gap near zero, or one that does not look like the coal and wine gaps, is the check "
            "that the basket is not inventing a stoppage."
        )
    engine = graph["engine"]
    duckpgq = graph.get("duckpgq_error") or "loaded"
    text = f"""# How the figures were made

The briefing answers a practical question: how much of Australia's goods-export income still depends on China, which of the blocked goods have come back, and where a second buyer already exists.

Pages are in plain language. This note keeps the method, the revision check and the limits.

Snapshot taken **{story["accessed"]}** (Australia/Melbourne). The latest published goods month in that extract is September 2026. The "latest year" on the pages is **{story["window_label"]}**.

## What is counted

- Source: ABS Data API, dataflow `ABS,MERCH_EXP,1.0.0`, merchandise exports by SITC revision 3 commodity, country of destination and state of origin, monthly from January 2006. Values are published in thousands of Australian dollars (`UNIT_MULT` 3) and stored as dollars.
- China is the code `CHIN`, "China (excludes SARs and Taiwan)". Hong Kong, Macau and Taiwan are separate buyers.
- Country groups (APEC, ASEAN, EU, OECD, developing-country totals) are not treated as buyers. "No country details" and "country not available" are not buyers either.
- A calendar year is finished when the national total has all 12 months. 2026 is not finished. It is kept out of the annual line and out of the "back / not back" test. The cards use the latest 12 months.
- The eight blocked groups are the official 3-digit groups that contain them. Wine is "alcoholic beverages", which also includes beer and spirits. Lobster is "crustaceans and molluscs", which also includes prawns. The page says so.
- ABS does not publish a zero. For those eight groups' sales to China, a missing month inside January 2006–September 2026 is treated as no recorded sales. That is what lines up with the coal, barley, wine, log and copper stoppages. Other series are left as published. Gold has missing years and is not used as a comparison good. Natural gas is published as a national total ({aud_text(story["exposure"]["gas_aud"])} in 2025) and not by destination.

## Buyer concentration

For each finished year, each country's share of the official national total is China's share on the chart. The score in the warehouse (Herfindahl-Hirschman) uses shares of the sum of individual countries, so the shares add to 1. It is not printed on the pages. The pages say what share the five biggest buyers took.

In 2006 China's share was {pct_text(next(row["share"] for row in story["exposure"]["history"] if row["year"] == 2006))}. In 2025 it was {pct_text_1(next(row["share"] for row in story["exposure"]["history"] if row["year"] == 2025))}. In the latest 12 months it was {story["exposure"]["kpis"][0]["value"]}.

## What "would have been" means

For each blocked good, a Bayesian synthetic control (CausalPy's `WeightedSumFitter`, PyMC) compares China sales of that good with a weighted basket of China sales of iron ore, wool, milk and fruit. Those four were not in the 2020–24 restriction list.

Weights have a Dirichlet prior, so they are positive and sum to 1. Before fitting, each comparison good is rescaled to the blocked good's average level in the years before the restriction. Otherwise iron ore, which is around $100 billion, cannot be averaged into a basket that matches barley. The blocked series stays in Australian dollars. The fit uses 200 draws and 200 tuning steps, 2 chains, seed 18. The likely range on the pages is the 5th to 95th percentile of the posterior.

The restriction year is the first calendar year that was mostly affected. Barley (May 2020) and the partial beef suspensions (from May 2020) start in 2020. Measures that began in October or November 2020 start in 2021, so 2020 stays in the pre-restriction fit. The shortfall is the gap during the restricted years only, not after the measure was lifted.

Pre-period error below is the average absolute gap before the restriction, divided by the pre-period average. Above about 35 percent, the page says the comparison is rough.

| Good | Restricted years | Shortfall, $ million | Likely range, $ million | Pre-period error | Weights |
| --- | --- | ---: | --- | ---: | --- |
{chr(10).join(model_lines)}

{placebo_line}

The pages do not use these model dollars. Wool's gap is large even though wool was not blocked, and several fits warn that the chains have not settled, so the briefing uses recorded sales against the 2017–19 average instead. That recorded shortfall is {aud_text(story["recovery"]["shortfall_total"])}.

Wheat is not in the basket. China bought much more wheat while barley was blocked, so wheat is not a picture of an undisturbed year.

## Second buyers

DuckPGQ does not ship a build for DuckDB 2.0.1. Installing it returns HTTP 404 from `extensions.duckdb.org` and from the community repository (`{duckpgq}`).

The buyer paths are a recursive SQL walk on the 2025 flow table. It starts at China, steps to each good China bought, then steps to every other buyer of that good. That is the two-step path a property-graph query would express. The engine recorded for this run is `{engine}`. A buyer is treated as a real second market when its 2025 purchases are at least half of China's, and separately when they are at least $20 million.

## Revision report

Two vintages of ABS Table 14a (merchandise exports by country, $ million) are in the snapshot:

- August 2026 release, reference month August 2026
- September 2026 release, reference month September 2026

The September release says merchandise exports were revised back to March 2026. The cell comparison agrees. China months before March 2026 are unchanged. September 2026 exists only in the later release, so it is a new month, not a revision.

Partner-months that moved by at least $0.5 million, excluding the total row: **{revision["cells"]}**. The absolute sum of those moves is **{aud_text(revision["abs_aud"])}**. Adding the total row on top of the countries would double-count, so the total is shown on its own.

China, $ million:

| Month | August release | September release | Change |
| --- | ---: | ---: | ---: |
{chr(10).join(china_lines)}

National total, months that moved by at least $0.5 million:

| Month | Change, $ million |
| --- | ---: |
{chr(10).join(total_lines)}

The September API figure for China in September 2026 matches the September workbook within $1 million. The build stops if it does not.

DuckLake keeps both vintages. The integration test loads the August release into a Postgres-catalogued lake with the files on the S3-compatible store, records the snapshot, replaces the table with the September release, and reads the August snapshot back with `AT (VERSION => …)`. The China cells from that time-travel read have to match the August parquet. A failed check does not get written into the briefing numbers. The numbers above are the direct difference of the two published workbooks, which is what the time-travel diff is checked against.

## Limits

- This is goods only. Education, tourism and other services are not in the file.
- Dollars are nominal. The exchange-rate chart is context, not a price adjustment. A weaker Australian dollar lifts Australian-dollar receipts even when foreign-currency prices do not.
- Confidential cells are real. About {aud_text(story["exposure"]["confidential_aud"])} of the latest year's sales to China are in a combined confidential item. Natural gas is missing from the country split entirely.
- State totals do not have to add to the national total. Re-exports and sales with no state are outside the eight states. In this extract the states' China sales are close to the national China total.
- The 10 percent figure is arithmetic: a tenth of recorded sales to China. It is not a model of prices, volumes, or what other buyers would do.
- The synthetic control is a comparison, not a prediction of what a minister should do. Beef was a partial plant suspension, not a closed market, and the result says so when the gap is not a loss.
- SITC groups are broader than the product that was named in the restriction. Read the notes on wine and shellfish before treating the dollars as pure lobster or pure wine.

## Not a forecast and not advice

Do not use these pages to price a cargo, brief a negotiation as if the gap were a damages number, or assume a second buyer can take iron ore at China's scale.
"""
    (ROOT / "INSIGHTS.md").write_text(text, encoding="utf-8")
