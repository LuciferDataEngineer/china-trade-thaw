# How the figures were made

The briefing answers a practical question: how much of Australia's goods-export income still depends on China, which of the blocked goods have come back, and where a second buyer already exists.

Pages are in plain language. This note keeps the method, the revision check and the limits.

Snapshot taken **21 November 2026, 9:37 AM AEDT** (Australia/Melbourne). The latest published goods month in that extract is September 2026. The "latest year" on the pages is **October 2025 to September 2026**.

## What is counted

- Source: ABS Data API, dataflow `ABS,MERCH_EXP,1.0.0`, merchandise exports by SITC revision 3 commodity, country of destination and state of origin, monthly from January 2006. Values are published in thousands of Australian dollars (`UNIT_MULT` 3) and stored as dollars.
- China is the code `CHIN`, "China (excludes SARs and Taiwan)". Hong Kong, Macau and Taiwan are separate buyers.
- Country groups (APEC, ASEAN, EU, OECD, developing-country totals) are not treated as buyers. "No country details" and "country not available" are not buyers either.
- A calendar year is finished when the national total has all 12 months. 2026 is not finished. It is kept out of the annual line and out of the "back / not back" test. The cards use the latest 12 months.
- The eight blocked groups are the official 3-digit groups that contain them. Wine is "alcoholic beverages", which also includes beer and spirits. Lobster is "crustaceans and molluscs", which also includes prawns. The page says so.
- ABS does not publish a zero. For those eight groups' sales to China, a missing month inside January 2006–September 2026 is treated as no recorded sales. That is what lines up with the coal, barley, wine, log and copper stoppages. Other series are left as published. Gold has missing years and is not used as a comparison good. Natural gas is published as a national total ($60.2 billion in 2025) and not by destination.

## Buyer concentration

For each finished year, each country's share of the official national total is China's share on the chart. The score in the warehouse (Herfindahl-Hirschman) uses shares of the sum of individual countries, so the shares add to 1. It is not printed on the pages. The pages say what share the five biggest buyers took.

In 2006 China's share was 12%. In 2025 it was 33.6%. In the latest 12 months it was 35.2%.

## What "would have been" means

For each blocked good, a Bayesian synthetic control (CausalPy's `WeightedSumFitter`, PyMC) compares China sales of that good with a weighted basket of China sales of iron ore, wool, milk and fruit. Those four were not in the 2020–24 restriction list.

Weights have a Dirichlet prior, so they are positive and sum to 1. Before fitting, each comparison good is rescaled to the blocked good's average level in the years before the restriction. Otherwise iron ore, which is around $100 billion, cannot be averaged into a basket that matches barley. The blocked series stays in Australian dollars. The fit uses 200 draws and 200 tuning steps, 2 chains, seed 18. The likely range on the pages is the 5th to 95th percentile of the posterior.

The restriction year is the first calendar year that was mostly affected. Barley (May 2020) and the partial beef suspensions (from May 2020) start in 2020. Measures that began in October or November 2020 start in 2021, so 2020 stays in the pre-restriction fit. The shortfall is the gap during the restricted years only, not after the measure was lifted.

Pre-period error below is the average absolute gap before the restriction, divided by the pre-period average. Above about 35 percent, the page says the comparison is rough.

| Good | Restricted years | Shortfall, $ million | Likely range, $ million | Pre-period error | Weights |
| --- | --- | ---: | --- | ---: | --- |
| Barley | 2020–2022 | 3989 | 3989 to 3989 | 40% | 281 0%, 268 63%, 022 37%, 057 0% |
| Wine and drinks | 2021–2023 | 3088 | 3076 to 3103 | 16% | 281 0%, 268 40%, 022 4%, 057 56% |
| Coal | 2021–2022 | 31880 | 31880 to 31881 | 28% | 281 26%, 268 48%, 022 17%, 057 9% |
| Shellfish | 2021–2024 | 2202 | 2202 to 2202 | 35% | 281 0%, 268 12%, 022 0%, 057 88% |
| Timber logs | 2021–2022 | 1593 | 1592 to 1593 | 28% | 281 0%, 268 35%, 022 46%, 057 19% |
| Beef | 2020–2023 | 515 | 513 to 518 | 30% | 281 35%, 268 0%, 022 0%, 057 65% |
| Cotton | 2021–2022 | 2391 | 2391 to 2391 | 64% | 281 39%, 268 61%, 022 0%, 057 0% |
| Copper ores | 2021–2022 | 5578 | 5566 to 5592 | 12% | 281 23%, 268 73%, 022 4%, 057 0% |

Wool, which was not blocked, was put through the same comparison as if a restriction had started in 2020 and lasted through 2022. The central gap is $10.2 billion (likely range $10.2 billion to $10.2 billion). A gap near zero, or one that does not look like the coal and wine gaps, is the check that the basket is not inventing a stoppage.

The pages do not use these model dollars. Wool's gap is large even though wool was not blocked, and several fits warn that the chains have not settled, so the briefing uses recorded sales against the 2017–19 average instead. That recorded shortfall is $41.2 billion.

Wheat is not in the basket. China bought much more wheat while barley was blocked, so wheat is not a picture of an undisturbed year.

## Second buyers

DuckPGQ does not ship a build for DuckDB 2.0.1. Installing it returns HTTP 404 from `extensions.duckdb.org` and from the community repository (`HTTP 404 from extensions.duckdb.org and the community repository for DuckDB 2.0.1 linux_amd64`).

The buyer paths are a recursive SQL walk on the 2025 flow table. It starts at China, steps to each good China bought, then steps to every other buyer of that good. That is the two-step path a property-graph query would express. The engine recorded for this run is `recursive-sql`. A buyer is treated as a real second market when its 2025 purchases are at least half of China's, and separately when they are at least $20 million.

## Revision report

Two vintages of ABS Table 14a (merchandise exports by country, $ million) are in the snapshot:

- August 2026 release, reference month August 2026
- September 2026 release, reference month September 2026

The September release says merchandise exports were revised back to March 2026. The cell comparison agrees. China months before March 2026 are unchanged. September 2026 exists only in the later release, so it is a new month, not a revision.

Partner-months that moved by at least $0.5 million, excluding the total row: **114**. The absolute sum of those moves is **$2.6 billion**. Adding the total row on top of the countries would double-count, so the total is shown on its own.

China, $ million:

| Month | August release | September release | Change |
| --- | ---: | ---: | ---: |
| 2026-03 | 17058 | 17053 | -5 |
| 2026-04 | 16956 | 16948 | -8 |
| 2026-05 | 16499 | 16472 | -27 |
| 2026-06 | 18850 | 18824 | -26 |
| 2026-07 | 15526 | 15546 | +20 |
| 2026-08 | 16069 | 16014 | -55 |
| 2026-09 | new month | 17102 | added in the September release |

National total, months that moved by at least $0.5 million:

| Month | Change, $ million |
| --- | ---: |
| 2026-03 | -5 |
| 2026-04 | +80 |
| 2026-05 | +145 |
| 2026-06 | +128 |
| 2026-07 | -96 |
| 2026-08 | -855 |

The September API figure for China in September 2026 matches the September workbook within $1 million. The build stops if it does not.

DuckLake keeps both vintages. The integration test loads the August release into a Postgres-catalogued lake with the files on the S3-compatible store, records the snapshot, replaces the table with the September release, and reads the August snapshot back with `AT (VERSION => …)`. The China cells from that time-travel read have to match the August parquet. A failed check does not get written into the briefing numbers. The numbers above are the direct difference of the two published workbooks, which is what the time-travel diff is checked against.

## Limits

- This is goods only. Education, tourism and other services are not in the file.
- Dollars are nominal. The exchange-rate chart is context, not a price adjustment. A weaker Australian dollar lifts Australian-dollar receipts even when foreign-currency prices do not.
- Confidential cells are real. About $18.9 billion of the latest year's sales to China are in a combined confidential item. Natural gas is missing from the country split entirely.
- State totals do not have to add to the national total. Re-exports and sales with no state are outside the eight states. In this extract the states' China sales are close to the national China total.
- The 10 percent figure is arithmetic: a tenth of recorded sales to China. It is not a model of prices, volumes, or what other buyers would do.
- The synthetic control is a comparison, not a prediction of what a minister should do. Beef was a partial plant suspension, not a closed market, and the result says so when the gap is not a loss.
- SITC groups are broader than the product that was named in the restriction. Read the notes on wine and shellfish before treating the dollars as pure lobster or pure wine.

## Not a forecast and not advice

Do not use these pages to price a cargo, brief a negotiation as if the gap were a damages number, or assume a second buyer can take iron ore at China's scale.
