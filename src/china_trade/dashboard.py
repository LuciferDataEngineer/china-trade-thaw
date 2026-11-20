"""Static briefing pages. No pipeline language on the pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from china_trade import charts
from china_trade.metrics import aud_text, pct_text, pct_text_1

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
STATIC = Path(__file__).resolve().parent / "static"
SNAPSHOT = ROOT / "data" / "snapshot"

PAGES = [
    ("index.html", "The exposure"),
    ("recovery.html", "What came back"),
    ("states.html", "By state"),
    ("grow.html", "Where to grow"),
]


def render(story: dict) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    assets = SITE / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(STATIC, assets)
    _favicon(SITE / "favicon.ico")
    pages = {
        "index.html": _exposure(story),
        "recovery.html": _recovery(story),
        "states.html": _states(story),
        "grow.html": _grow(story),
    }
    for name, body in pages.items():
        (SITE / name).write_text(_page(name, body, story), encoding="utf-8")
    (SITE / "story.json").write_text(json.dumps(_public_story(story), indent=2), encoding="utf-8")


def _page(filename: str, body: str, story: dict) -> str:
    tabs = []
    for name, label in PAGES:
        current = ' aria-current="page"' if name == filename else ""
        tabs.append(f'<a href="{name}"{current}>{label}</a>')
    return f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_title(filename)} · China trade thaw</title>
<link rel="icon" href="favicon.ico">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="top">
  <div class="brand">China trade thaw</div>
  <nav>{"".join(tabs)}</nav>
</header>
<main>
{body}
<footer class="sources">
  <p>Goods exports are published by the Australian Bureau of Statistics, merchandise trade, free under CC BY 4.0.
  Exchange rates are the Reserve Bank of Australia's public tables. State outlines are Natural Earth, public domain.
  China here excludes Hong Kong, Macau and Taiwan, which are published separately.
  Figures were taken on {story["accessed"]}, Australia/Melbourne time.
  Dollars are Australian dollars, not adjusted for inflation.</p>
</footer>
</main>
<script src="assets/app.js"></script>
</body>
</html>
"""


def _exposure(story: dict) -> str:
    exposure = story["exposure"]
    history = charts.line_chart(
        [{"year": row["year"], "value": row["share"] * 100} for row in exposure["history"]],
        chart_id="china-share",
        y_format=lambda value: f"{value:.0f}%",
        callouts=[2006, 2019, 2022, 2025],
    )
    commodities = charts.hbar(
        [
            {
                "label": row["label"],
                "value": row["aud"],
                "display": aud_text(row["aud"]),
                "swatch": "#ffc857" if row["confidential"] else "#2ee6c7",
            }
            for row in exposure["commodities"]
        ],
        chart_id="china-goods",
        colour_key="swatch",
    )
    partners = charts.hbar(
        [
            {"label": row["label"], "value": row["aud"], "display": aud_text(row["aud"])}
            for row in exposure["partners"]
        ],
        chart_id="partners",
    )
    fx = charts.line_chart(
        [{"year": row["year"], "value": row["usd"]} for row in story["fx"]["series"]],
        chart_id="aud-usd",
        y_format=lambda value: f"{value:.2f}",
        callouts=[2019, 2025],
    )
    gas = exposure["gas_aud"]
    gas_line = (
        f" Natural gas, {aud_text(gas)} in 2025, is not published by destination, so it is not in the China list."
        if gas
        else ""
    )
    return f"""
<section class="banner">
  <p class="kicker">The exposure</p>
  <h1>{_esc(exposure["headline"])}</h1>
</section>
<section class="kpis">{_kpis(exposure["kpis"])}</section>
<section class="card">
  <h2>China's share rose from 12 percent in 2006, dipped in 2022, and is about a third again</h2>
  {history}
  <p class="note">Each point is a finished calendar year. 2026 is still underway, so it is not on this line. The cards use {
        _esc(story["window_label"])
    }.</p>
  {
        _values(
            "China share by calendar year",
            [
                [
                    str(row["year"]),
                    pct_text_1(row["share"]),
                    aud_text(row["china_aud"]),
                    aud_text(row["total_aud"]),
                ]
                for row in exposure["history"]
            ],
            ["Year", "China share", "Sales to China", "All goods exports"],
        )
    }
</section>
<section class="grid-2">
  <article class="card">
    <h2>Iron ore is still half of what Australia sells to China</h2>
    {commodities}
    <p class="note">Latest 12 months. “Confidential, not named” is {
        aud_text(exposure["confidential_aud"])
    } of sales the ABS will not split into products.{_esc(gas_line)}</p>
    {
        _values(
            "Sales to China by product, latest 12 months",
            [
                [row["label"], aud_text(row["aud"]), pct_text_1(row["share"])]
                for row in exposure["commodities"]
            ],
            ["Product", "Sales to China", "Share of China sales"],
        )
    }
  </article>
  <article class="card">
    <h2>Japan is a distant second</h2>
    {partners}
    <p class="note">{_esc(story["fx"]["sentence"])}</p>
    {fx}
    {
        _values(
            "Largest buyers, latest 12 months",
            [
                [row["label"], aud_text(row["aud"]), pct_text_1(row["share"])]
                for row in exposure["partners"]
            ],
            ["Buyer", "Goods exports", "Share of all goods"],
        )
    }
  </article>
</section>
{_means(exposure["means"])}
"""


def _recovery(story: dict) -> str:
    recovery = story["recovery"]
    overview = charts.hbar(
        [
            {
                "label": good["short"],
                "value": good["ratio"] * 100,
                "display": pct_text(good["ratio"]),
                "swatch": {"back": "#2ee6c7", "part": "#ffc857", "down": "#ff6b6b"}[good["status"]],
            }
            for good in recovery["goods"]
        ],
        chart_id="recovery-ratio",
        colour_key="swatch",
    )
    button_html = []
    panel_html = []
    for index, good in enumerate(recovery["goods"]):
        button_html.append(
            f'<button type="button" class="{"on" if index == 0 else ""}" '
            f'data-panel="{good["sitc"]}" aria-pressed="{"true" if index == 0 else "false"}">'
            f"{_esc(good['short'])}</button>"
        )
        hidden = "" if index == 0 else " hidden"
        annual = charts.annual_compare(
            [
                {
                    "year": point["year"],
                    "actual": point["aud"] / 1e6,
                    "low": None,
                    "high": None,
                }
                for point in good["annual"]
            ],
            chart_id=f"annual-{good['sitc']}",
        )
        monthly = charts.spark(good["monthly"], chart_id=f"month-{good['sitc']}")
        ytd = ""
        if good["ytd"] > good["y2025"]:
            ytd = (
                f" In the first nine months of 2026, sales were already {aud_text(good['ytd'])}, "
                "above the whole of 2025."
            )
        panel_html.append(
            f"""
<div class="panel" data-panel-id="{good["sitc"]}"{hidden}>
  <h3>{_esc(good["plain"])}: 2025 was {pct_text(good["ratio"])} of the 2017–19 average</h3>
  <p class="note">{_esc(good["note"])} {_esc(_loss_sentence(good))}{_esc(ytd)}</p>
  {annual}
  <p class="note">Bars are recorded sales, in millions of Australian dollars, for each finished year from 2017 to 2025.</p>
  {monthly}
  <p class="note">Month by month since 2018. A flat stretch on the baseline is a run of months with no recorded sales.</p>
  {
                _values(
                    good["plain"] + ", calendar years",
                    [
                        [
                            str(point["year"]),
                            aud_text(point["aud"]),
                            ""
                            if point.get("prediction") is None
                            else aud_text(point["prediction"]),
                            ""
                            if point.get("low") is None
                            else aud_text(point["low"]) + " to " + aud_text(point["high"]),
                        ]
                        for point in good["annual"]
                    ],
                    ["Year", "Recorded", "Would have been", "Likely range"],
                )
            }
</div>
"""
        )
    return f"""
<section class="banner">
  <p class="kicker">What came back</p>
  <h1>{_esc(recovery["headline"])}</h1>
</section>
<section class="kpis">{_kpis(_recovery_kpis(recovery))}</section>
<section class="card">
  <h2>100 percent would mean 2025 matched the years just before the blocks</h2>
  {overview}
  <p class="note">Green is back to at least 90 percent. Amber is part way. Red is still well short. Beef was not a full ban.</p>
  {
        _values(
            "2025 China sales against 2017–19",
            [
                [
                    good["short"],
                    aud_text(good["pre"]),
                    aud_text(good["during"]),
                    aud_text(good["y2025"]),
                    pct_text(good["ratio"]),
                ]
                for good in recovery["goods"]
            ],
            ["Good", "2017–19 average", "Blocked years", "2025", "2025 vs old level"],
        )
    }
</section>
<section class="card" data-switch>
  <div class="pills">{"".join(button_html)}</div>
  {"".join(panel_html)}
</section>
{_means(recovery["means"] + (" " + recovery["wheat"] if recovery["wheat"] else ""))}
"""


def _states(story: dict) -> str:
    states = story["states"]
    features = json.loads((SNAPSHOT / "au_states.geojson").read_text())["features"]
    shares = {row["name"]: row["share"] for row in states["rows"]}
    drawing = charts.australia_map(features, shares, chart_id="state-map")
    bars = charts.hbar(
        [
            {
                "label": row["name"]
                .replace("Australian Capital Territory", "ACT")
                .replace("New South Wales", "NSW")
                .replace("South Australia", "SA")
                .replace("Western Australia", "WA")
                .replace("Northern Territory", "NT"),
                "value": row["shock"],
                "display": aud_text(row["shock"]),
            }
            for row in states["rows"]
        ],
        chart_id="state-shock",
        label_width=120,
    )
    return f"""
<section class="banner">
  <p class="kicker">By state</p>
  <h1>{_esc(states["headline"])}</h1>
</section>
<section class="kpis">{_kpis(states["kpis"])}</section>
<section class="grid-2">
  <article class="card">
    <h2>The west depends on China. The dollars are there too</h2>
    {drawing}
    <ul class="legend">
      <li><i style="background:#ff6b6b"></i> Over 45 percent</li>
      <li><i style="background:#ffc857"></i> 28 to 45 percent</li>
      <li><i style="background:#2ee6c7"></i> 12 to 28 percent</li>
      <li><i style="background:#3d5168"></i> Under 12 percent</li>
    </ul>
    <p class="note">Share of each state's goods exports that went to China, {
        _esc(states["window_label"])
    }. The ACT has no published China sales in this window.</p>
  </article>
  <article class="card">
    <h2>Dollars at stake if China sales fall by a tenth</h2>
    {bars}
    {
        _values(
            "State goods exports, latest 12 months",
            [
                [
                    row["name"],
                    aud_text(row["total"]),
                    aud_text(row["china"]),
                    pct_text_1(row["share"]),
                    aud_text(row["shock"]),
                ]
                for row in states["rows"]
            ],
            ["State", "All goods", "To China", "China share", "10 percent of China sales"],
        )
    }
  </article>
</section>
{_means(states["means"])}
"""


def _grow(story: dict) -> str:
    grow = story["grow"]
    buttons = []
    panels = []
    for card in grow["cards"]:
        selected = card["sitc"] == grow["default"]
        buttons.append(
            f'<button type="button" class="{"on" if selected else ""}" data-panel="{card["sitc"]}" '
            f'aria-pressed="{"true" if selected else "false"}">{_esc(card["plain"])}</button>'
        )
        hidden = "" if selected else " hidden"
        chart = charts.hbar(
            [
                {
                    "label": buyer["label"],
                    "value": buyer["aud"],
                    "display": aud_text(buyer["aud"]),
                    "swatch": "#ff6b6b" if buyer["code"] == "CHIN" else "#6cb6ff",
                }
                for buyer in card["buyers"]
            ],
            chart_id=f"buyers-{card['sitc']}",
            colour_key="swatch",
        )
        if card["serious"]:
            takeaway = (
                f"{card['next_label']} already buys {aud_text(card['next_aud'])}, "
                f"{pct_text(card['ratio'])} of China's {aud_text(card['china'])}."
            )
        else:
            takeaway = (
                f"{card['next_label']} buys {aud_text(card['next_aud'])}. "
                f"That is {pct_text(card['ratio'])} of China's {aud_text(card['china'])}."
            )
        panels.append(
            f"""
<div class="panel" data-panel-id="{card["sitc"]}"{hidden}>
  <h3>{_esc(takeaway)}</h3>
  {chart}
  <p class="note">2025, the last finished year. China is in coral. Other buyers already taking the product are in blue.</p>
  {
                _values(
                    card["plain"] + " buyers in 2025",
                    [[buyer["label"], aud_text(buyer["aud"])] for buyer in card["buyers"]],
                    ["Buyer", "Purchases"],
                )
            }
</div>
"""
        )
    return f"""
<section class="banner">
  <p class="kicker">Where to grow</p>
  <h1>{_esc(grow["headline"])}</h1>
</section>
<section class="kpis">{_kpis(grow["kpis"])}</section>
<section class="card" data-switch>
  <div class="pills">{"".join(buttons)}</div>
  {"".join(panels)}
</section>
{_means(grow["means"])}
"""


def _recovery_kpis(recovery: dict) -> list[dict]:
    goods = {good["short"]: good for good in recovery["goods"]}
    wine = goods.get("Wine and drinks")
    return [
        {
            "label": "Back near the old level",
            "value": str(len(recovery["back"])),
            "detail": ", ".join(recovery["back"]) or "None",
            "status": "back",
        },
        {
            "label": "Only part way back",
            "value": str(len(recovery["part"])),
            "detail": ", ".join(recovery["part"]) or "None",
            "status": "part",
        },
        {
            "label": "Still well short",
            "value": str(len(recovery["down"])),
            "detail": ", ".join(recovery["down"]) or "None",
            "status": "down" if recovery["down"] else "back",
        },
        {
            "label": "Below the old average",
            "value": aud_text(recovery["shortfall_total"]),
            "detail": "recorded sales during the blocked years",
            "status": "down",
        },
        {
            "label": "Wine in 2025",
            "value": pct_text(wine["ratio"]) if wine else "–",
            "detail": "of the 2017–19 China average" if wine else "",
            "status": wine["status"] if wine else "part",
        },
    ]


def _loss_sentence(good: dict) -> str:
    gap = good.get("recorded_gap") or 0
    if gap <= 0:
        return "Recorded sales in the blocked years stayed at or above the 2017–19 average."
    return f"In the blocked years, recorded sales were {aud_text(gap)} below the 2017–19 average."


def _kpis(items: list[dict]) -> str:
    cards = []
    for item in items:
        cards.append(
            f'<article class="kpi status-{item["status"]}">'
            f'<p class="kpi-label">{_esc(item["label"])}</p>'
            f'<p class="kpi-value">{_esc(item["value"])}</p>'
            f'<p class="kpi-detail">{_esc(item["detail"])}</p>'
            f"</article>"
        )
    return "".join(cards)


def _means(text: str) -> str:
    return f'<section class="means"><h2>What this means</h2><p>{_esc(text)}</p></section>'


def _values(title: str, rows: list[list[str]], headers: list[str]) -> str:
    head = "".join(f"<th>{_esc(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f'<details class="exact"><summary>Exact values · {_esc(title)}</summary>'
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></details>"
    )


def _title(filename: str) -> str:
    return dict(PAGES)[filename]


def _esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _public_story(story: dict) -> dict:
    """Drop monthly series so the JSON beside the site stays small."""
    recovery = dict(story["recovery"])
    recovery["goods"] = [
        {key: value for key, value in good.items() if key != "monthly"}
        for good in recovery["goods"]
    ]
    return {**story, "recovery": recovery}


def _favicon(path: Path) -> None:
    import struct
    import zlib

    width = height = 16
    rgba = bytes([23, 214, 184, 255]) * (width * height)
    raw = b"".join(b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(png), 22)
    path.write_bytes(header + entry + png)
