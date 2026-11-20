"""Names and rules that sit on top of the ABS codelists.

Plain-language names are for the briefing. ABS names stay in the data files.
"""

from __future__ import annotations

# Statistical groupings in MERCH_EXP. They repeat country detail, so they are
# not buyers in a concentration or "second market" calculation.
AGGREGATE_COUNTRIES = frozenset({"TOT", "APEC", "ASEAN", "DC", "LDC", "EURO27", "EURO", "OECD"})

# Joint Petroleum Development Area is a zone, not a promotion market.
EXCLUDED_MARKETS = AGGREGATE_COUNTRIES | {"JPDA"}

STATE_NAMES = {
    "1": "New South Wales",
    "2": "Victoria",
    "3": "Queensland",
    "4": "South Australia",
    "5": "Western Australia",
    "6": "Tasmania",
    "7": "Northern Territory",
    "8": "Australian Capital Territory",
}

STATE_SHORT = {
    "1": "NSW",
    "2": "Vic",
    "3": "Qld",
    "4": "SA",
    "5": "WA",
    "6": "Tas",
    "7": "NT",
    "8": "ACT",
}

# First full calendar year of the restriction, and the first full calendar year
# after the restriction was lifted. 2020 is only used when the measure started
# early enough to dominate that year (barley in May, beef plants from May).
# Measures that started in October or November are treated as starting in 2021.
RESTRICTED = {
    "043": {
        "plain": "Barley",
        "short": "Barley",
        "treat": 2020,
        "lift": 2023,
        "note": "Extra tariffs from May 2020 were removed in August 2023.",
    },
    "112": {
        "plain": "Wine and other alcoholic drinks",
        "short": "Wine and drinks",
        "treat": 2021,
        "lift": 2024,
        "note": (
            "Wine tariffs from November 2020 were removed in March 2024. "
            "Beer and spirits sit in the same official group."
        ),
    },
    "321": {
        "plain": "Coal",
        "short": "Coal",
        "treat": 2021,
        "lift": 2023,
        "note": "Informal restrictions from around October 2020 were cleared by early 2023.",
    },
    "036": {
        "plain": "Lobster and other shellfish",
        "short": "Shellfish",
        "treat": 2021,
        "lift": 2025,
        "note": (
            "Live rock lobster stopped in November 2020 and could restart in December 2024. "
            "Prawns and other shellfish are in the same official group."
        ),
    },
    "247": {
        "plain": "Rough timber logs",
        "short": "Timber logs",
        "treat": 2021,
        "lift": 2023,
        "note": "Log shipments stopped in late 2020 and resumed during 2023.",
    },
    "011": {
        "plain": "Beef",
        "short": "Beef",
        "treat": 2020,
        "lift": 2024,
        "note": "Some beef plants were suspended from May 2020. It was not a ban on all beef.",
    },
    "263": {
        "plain": "Raw cotton",
        "short": "Cotton",
        "treat": 2021,
        "lift": 2023,
        "note": "Restrictions from late 2020 were lifted during 2023.",
    },
    "283": {
        "plain": "Copper ores",
        "short": "Copper ores",
        "treat": 2021,
        "lift": 2023,
        "note": "Informal restrictions from late 2020 eased during 2023.",
    },
}

# Unrestricted China-bound goods used as the comparison basket.
# Wheat is left out: China bought much more of it while barley was blocked.
# Gold has unpublished years. Natural gas is not published by destination.
DONORS = {
    "281": "Iron ore",
    "268": "Wool",
    "022": "Milk and cream",
    "057": "Fruit and nuts",
}

PLACEBO_SITC = "268"
PLACEBO_NAME = "Wool"

# Partners downloaded in full, so the briefing can name a second buyer.
FOCUS_SITC = list(dict.fromkeys([*RESTRICTED.keys(), *DONORS.keys()]))

PARTNER_PLAIN = {
    "CHIN": "China",
    "JAP": "Japan",
    "RKOR": "South Korea",
    "USA": "United States",
    "UK": "United Kingdom",
    "INIA": "India",
    "TAIW": "Taiwan",
    "HONG": "Hong Kong",
    "INDO": "Indonesia",
    "NZ": "New Zealand",
    "SING": "Singapore",
    "MLAY": "Malaysia",
    "VIET": "Vietnam",
    "THAI": "Thailand",
    "SAUD": "Saudi Arabia",
    "MEX": "Mexico",
    "NCD": "No country published",
    "CNAV": "Country not available",
}

PRE_YEARS = (2017, 2018, 2019)
SHOCK = 0.10
# A buyer counts as a real second market above this annual value.
MARKET_FLOOR_AUD = 20_000_000

ABS_FLOW = "https://data.api.abs.gov.au/rest/data/ABS,MERCH_EXP,1.0.0/"
ABS_STRUCTURE = "https://data.api.abs.gov.au/rest/dataflow/ABS/MERCH_EXP?references=all&detail=full"
ABS_RELEASE = {
    "2026-08": (
        "https://www.abs.gov.au/statistics/economy/international-trade/"
        "international-trade-goods/aug-2026/5368014a.xlsx"
    ),
    "2026-09": (
        "https://www.abs.gov.au/statistics/economy/international-trade/"
        "international-trade-goods/sep-2026/5368014a.xlsx"
    ),
}
RBA_FX = "https://www.rba.gov.au/statistics/tables/csv/f11-data.csv"
RBA_FX_RECENT = "https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv"
# The 110m admin-1 extract on GitHub currently contains only US states.
# The 50m extract includes every Australian state and territory. Public domain.
NATURAL_EARTH = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_1_states_provinces.geojson"
)
