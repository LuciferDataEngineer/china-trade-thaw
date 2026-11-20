"""SVG charts with room set aside for every label."""

from __future__ import annotations

import math
from collections.abc import Sequence

PALETTE = ["#2ee6c7", "#ffc857", "#6cb6ff", "#ff8b6b", "#c9a6ff", "#b6f25c", "#7ee0ff"]


def _esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def hbar(
    rows: Sequence[dict],
    *,
    chart_id: str,
    value_key: str = "value",
    label_key: str = "label",
    colour_key: str | None = None,
    width: int = 720,
    label_width: int = 168,
    value_width: int = 108,
) -> str:
    if not rows:
        return "<p>No figures for this chart.</p>"
    top = max(float(row[value_key]) for row in rows) or 1.0
    row_h = 34
    height = row_h * len(rows) + 8
    bar_left = label_width + 8
    bar_right = width - value_width - 8
    bar_span = max(bar_right - bar_left, 20)
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    for index, row in enumerate(rows):
        y = 6 + index * row_h
        value = float(row[value_key])
        colour = row.get(colour_key) if colour_key else PALETTE[index % len(PALETTE)]
        length = 0 if top <= 0 else bar_span * max(value, 0) / top
        parts.append(
            f'<text class="chart-label" x="8" y="{y + 18}" fill="#d5e2ef" font-size="14">'
            f"{_esc(row[label_key])}</text>"
        )
        parts.append(
            f'<rect x="{bar_left}" y="{y + 6}" width="{length:.1f}" height="16" rx="3" '
            f'fill="{colour}"></rect>'
        )
        parts.append(
            f'<text class="chart-label" x="{width - 4}" y="{y + 18}" text-anchor="end" '
            f'fill="#f4f7fb" font-size="14">{_esc(row.get("display", value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def line_chart(
    series: Sequence[dict],
    *,
    chart_id: str,
    width: int = 720,
    height: int = 320,
    y_format=None,
    callouts: Sequence[int] | None = None,
) -> str:
    """One line. ``series`` items need year and value. Years must be in order."""
    if len(series) < 2:
        return "<p>Not enough years to draw this chart.</p>"
    y_format = y_format or (lambda v: f"{v:.0f}")
    left, right, top, bottom = 64, 36, 28, 40
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [float(row["value"]) for row in series]
    years = [int(row["year"]) for row in series]
    low = min(0.0, min(values))
    high = max(values) * 1.12 or 1.0
    span = high - low or 1.0
    ticks = [max(values), (max(values) + low) / 2, low]

    def x_at(index: int) -> float:
        return left + plot_w * index / (len(series) - 1)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - (value - low) / span)

    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    for tick in ticks:
        y = y_at(tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="#2c3c4e"></line>'
        )
        parts.append(
            f'<text class="chart-label" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="#93a4b8" font-size="12">{_esc(y_format(tick))}</text>'
        )
    parts.append(
        f'<polyline fill="none" stroke="#2ee6c7" stroke-width="2.5" points="{points}"></polyline>'
    )
    last = len(years) - 1
    for index, year in enumerate(years):
        if index != last and (index % 3 != 0 or last - index < 2):
            continue
        parts.append(
            f'<text class="chart-label year-label" data-year="{year}" x="{x_at(index):.1f}" '
            f'y="{height - 10}" text-anchor="middle" fill="#93a4b8" font-size="12">{year}</text>'
        )
    chosen = list(callouts or [])
    if not chosen:
        chosen = [years[0], years[values.index(min(values))], years[-1]]
    callout_y = []
    callout_meta = []
    for year in dict.fromkeys(chosen):
        if year not in years:
            continue
        index = years.index(year)
        callout_meta.append((index, year, values[index]))
        callout_y.append(y_at(values[index]) - 10)
    nudged = _nudge(callout_y, 16, top + 12, top + plot_h - 4)
    last_index = len(series) - 1
    for (index, year, value), y in zip(callout_meta, nudged, strict=True):
        if index >= last_index - 1:
            anchor = "end"
            x = x_at(index) - 6
        else:
            anchor = "start"
            x = x_at(index) + 6
        parts.append(
            f'<text class="chart-label" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'fill="#f4f7fb" font-size="13">{_esc(y_format(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def spark(rows: Sequence[dict], *, chart_id: str, width: int = 720, height: int = 180) -> str:
    if len(rows) < 2:
        return "<p>Not enough months to draw this chart.</p>"
    values = [float(row["aud"]) for row in rows]
    left, right, top, bottom = 16, 16, 12, 28
    plot_w = width - left - right
    plot_h = height - top - bottom
    peak = max(values) * 1.1 or 1.0

    def x_at(index: int) -> float:
        return left + plot_w * index / (len(rows) - 1)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - value / peak)

    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
        f'<polyline fill="none" stroke="#6cb6ff" stroke-width="2" points="{points}"></polyline>'
    ]
    for index in (0, len(rows) - 1):
        year = rows[index]["period"][:4]
        parts.append(
            f'<text class="chart-label year-label" data-year="{year}" x="{x_at(index):.1f}" '
            f'y="{height - 8}" text-anchor="{"start" if index == 0 else "end"}" '
            f'fill="#93a4b8" font-size="12">{_esc(rows[index]["period"])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def annual_compare(
    rows: Sequence[dict],
    *,
    chart_id: str,
    width: int = 720,
    height: int = 300,
) -> str:
    """Bars for recorded sales and a band for the comparison."""
    if not rows:
        return "<p>No figures for this chart.</p>"
    left, right, top, bottom = 56, 12, 16, 32
    plot_w = width - left - right
    plot_h = height - top - bottom
    highs = [float(row["actual"]) for row in rows]
    highs += [float(row["high"]) for row in rows if row.get("high") is not None]
    peak = max(highs) * 1.08 or 1.0
    slot = plot_w / len(rows)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - value / peak)

    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    band = []
    band_back = []
    for index, row in enumerate(rows):
        if row.get("low") is None:
            continue
        x = left + slot * index + slot / 2
        band.append(f"{x:.1f},{y_at(float(row['high'])):.1f}")
        band_back.append(f"{x:.1f},{y_at(float(row['low'])):.1f}")
    if band:
        points = " ".join(band + list(reversed(band_back)))
        parts.append(f'<polygon points="{points}" fill="#ffc857" opacity="0.28"></polygon>')
    for index, row in enumerate(rows):
        x = left + slot * index + slot * 0.22
        actual = float(row["actual"])
        y = y_at(actual)
        base = y_at(0)
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{slot * 0.56:.1f}" height="{max(base - y, 0):.1f}" '
            f'rx="2" fill="#2ee6c7"></rect>'
        )
        year = int(row["year"])
        parts.append(
            f'<text class="chart-label year-label" data-year="{year}" x="{left + slot * index + slot / 2:.1f}" '
            f'y="{height - 8}" text-anchor="middle" fill="#93a4b8" font-size="12">{year}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def australia_map(features: Sequence[dict], values: dict[str, float], *, chart_id: str) -> str:
    projected = [_project_feature(feature) for feature in features]
    xs = [x for feature in projected for x, _y in feature["points"]]
    ys = [y for feature in projected for _x, y in feature["points"]]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width, height = 680, 560
    pad = 46
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)

    def sx(x: float) -> float:
        return pad + (x - min_x) * scale

    def sy(y: float) -> float:
        return pad + (max_y - y) * scale

    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    labels = []
    for feature in projected:
        share = values.get(feature["name"], 0.0)
        colour = _share_colour(share)
        for ring in feature["rings"]:
            coords = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in ring)
            parts.append(
                f'<polygon points="{coords}" fill="{colour}" stroke="#0e141b" '
                f'stroke-width="1.2"></polygon>'
            )
        cx, cy = feature["centroid"]
        short = _STATE_SHORT[feature["name"]]
        nudge_x, nudge_y = _NUDGE.get(short, (0, 0))
        labels.append((sx(cx) + nudge_x, sy(cy) + nudge_y, short))
    for x, y, short in labels:
        parts.append(
            f'<text class="chart-label" x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
            f'fill="#f7fbff" font-size="14" font-weight="700">{short}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


_STATE_SHORT = {
    "New South Wales": "NSW",
    "Victoria": "Vic",
    "Queensland": "Qld",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "Tas",
    "Northern Territory": "NT",
    "Australian Capital Territory": "ACT",
}
_NUDGE = {
    "ACT": (22, -16),
    "Tas": (0, 20),
    "Vic": (10, 12),
    "NSW": (12, 2),
    "SA": (-6, 10),
    "NT": (0, -8),
    "Qld": (8, 6),
    "WA": (0, 8),
}


def _share_colour(share: float) -> str:
    if share >= 0.45:
        return "#ff6b6b"
    if share >= 0.28:
        return "#ffc857"
    if share >= 0.12:
        return "#2ee6c7"
    return "#3d5168"


def _project_feature(feature: dict) -> dict:
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry["coordinates"]
    rings = []
    best = None
    best_area = -1.0
    for polygon in polygons:
        outer = polygon[0]
        projected = [_albers(lon, lat) for lon, lat in outer]
        rings.append(projected)
        area = abs(_shoelace(projected))
        if area > best_area:
            best_area = area
            best = projected
    centroid = _centroid(best or rings[0])
    return {
        "name": feature["properties"]["name"],
        "rings": rings,
        "points": [point for ring in rings for point in ring],
        "centroid": centroid,
    }


def _albers(lon: float, lat: float) -> tuple[float, float]:
    phi = math.radians(lat)
    lam = math.radians(lon)
    phi1 = math.radians(-18)
    phi2 = math.radians(-36)
    phi0 = math.radians(-27)
    lam0 = math.radians(134)
    n = 0.5 * (math.sin(phi1) + math.sin(phi2))
    c = math.cos(phi1) ** 2 + 2 * n * math.sin(phi1)
    rho0 = math.sqrt(c - 2 * n * math.sin(phi0)) / n
    rho = math.sqrt(c - 2 * n * math.sin(phi)) / n
    theta = n * (lam - lam0)
    return rho * math.sin(theta), rho0 - rho * math.cos(theta)


def _shoelace(points: Sequence[tuple[float, float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=False):
        area += x1 * y2 - x2 * y1
    return area / 2


def _centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    area = _shoelace(points)
    if abs(area) < 1e-12:
        return (
            sum(x for x, _y in points) / len(points),
            sum(y for _x, y in points) / len(points),
        )
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=False):
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return cx / (6 * area), cy / (6 * area)


def _nudge(ys: Sequence[float], gap: float, low: float, high: float) -> list[float]:
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    placed = [0.0] * len(ys)
    cursor = low
    for index in order:
        y = min(max(ys[index], cursor), high)
        placed[index] = y
        cursor = y + gap
    return placed
