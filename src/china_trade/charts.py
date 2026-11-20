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


def _ink(text: object, font: float) -> float:
    """Conservative width so a label stays inside the lane reserved for it."""
    return max(len(str(text)), 1) * font * 0.62


def _wrap(svg: str) -> str:
    return f'<div class="chart-scroll">{svg}</div>'


def hbar(
    rows: Sequence[dict],
    *,
    chart_id: str,
    value_key: str = "value",
    label_key: str = "label",
    colour_key: str | None = None,
    width: int = 720,
    font: int = 26,
    row_h: int | None = None,
    sorted_desc: bool = False,
) -> str:
    if not rows:
        return "<p>No figures for this chart.</p>"
    row_h = row_h or max(int(font * 2.45), font + 18)
    top = max(float(row[value_key]) for row in rows) or 1.0
    label_w = max(_ink(row[label_key], font) for row in rows) + font * 0.8
    value_w = max(_ink(row.get("display", ""), font) for row in rows) + font * 0.7
    if label_w + value_w + 28 > width:
        spare = width - 28
        label_w = spare * label_w / (label_w + value_w)
        value_w = spare - label_w
    height = row_h * len(rows) + 10
    bar_left = label_w + 8
    bar_right = width - value_w - 8
    bar_span = max(bar_right - bar_left, 20)
    bar_h = max(14, int(font * 0.78))
    sort_attr = ' data-sort="desc"' if sorted_desc else ""
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}"{sort_attr} '
        f'viewBox="0 0 {width} {height}" role="img" width="100%">'
    ]
    for index, row in enumerate(rows):
        y = 6 + index * row_h
        value = float(row[value_key])
        colour = row.get(colour_key) if colour_key else PALETTE[index % len(PALETTE)]
        length = 0 if top <= 0 else bar_span * max(value, 0) / top
        code = row.get("code")
        code_attr = f' data-code="{_esc(code)}"' if code else ""
        label_fill = row.get("label_fill", "#d5e2ef")
        text_y = y + row_h * 0.62
        bar_y = y + (row_h - bar_h) / 2
        parts.append(
            f'<text class="chart-label" x="8" y="{text_y:.1f}" fill="{label_fill}" '
            f'font-size="{font}">{_esc(row[label_key])}</text>'
        )
        parts.append(
            f'<rect x="{bar_left:.1f}" y="{bar_y:.1f}" width="{length:.1f}" height="{bar_h}" '
            f'rx="3" fill="{colour}"{code_attr}></rect>'
        )
        parts.append(
            f'<text class="chart-label" x="{width - 6}" y="{text_y:.1f}" text-anchor="end" '
            f'fill="#f4f7fb" font-size="{font}">{_esc(row.get("display", value))}</text>'
        )
    parts.append("</svg>")
    return _wrap("".join(parts))


def line_chart(
    series: Sequence[dict],
    *,
    chart_id: str,
    width: int = 720,
    height: int = 360,
    y_format=None,
    callouts: Sequence[int] | None = None,
    include_zero: bool = False,
    font: int = 26,
) -> str:
    """One line. ``series`` items need year and value. Years must be in order."""
    if len(series) < 2:
        return "<p>Not enough years to draw this chart.</p>"
    y_format = y_format or (lambda value: f"{value:.0f}")
    sample = y_format(max(float(row["value"]) for row in series))
    left = max(64, int(_ink(sample, font) + 18))
    right, top, bottom = 28, int(font + 16), int(font + 22)
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [float(row["value"]) for row in series]
    years = [int(row["year"]) for row in series]
    ticks = _nice_ticks(values, include_zero=include_zero)
    low, high = ticks[0], ticks[-1]
    span = high - low or 1.0

    def x_at(index: int) -> float:
        return left + plot_w * index / (len(series) - 1)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - (value - low) / span)

    points = [(x_at(i), y_at(value)) for i, value in enumerate(values)]
    point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
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
            f'<text class="chart-label tick" x="{left - 10}" y="{y - font * 0.08:.1f}" '
            f'text-anchor="end" fill="#93a4b8" font-size="{font}">{_esc(y_format(tick))}</text>'
        )
    parts.append(
        f'<polyline fill="none" stroke="#2ee6c7" stroke-width="2.5" points="{point_attr}"></polyline>'
    )
    peak_index = max(range(len(values)), key=lambda index: values[index])
    parts.append(
        f'<circle data-peak-point="1" data-year="{years[peak_index]}" '
        f'cx="{points[peak_index][0]:.1f}" cy="{points[peak_index][1]:.1f}" r="4.5" '
        f'fill="#f4f7fb" stroke="#2ee6c7" stroke-width="2"></circle>'
    )
    last = len(years) - 1
    for index, year in enumerate(years):
        if index != last and (index % 3 != 0 or last - index < 2):
            continue
        if index == 0:
            anchor = "start"
        elif index == last:
            anchor = "end"
        else:
            anchor = "middle"
        parts.append(
            f'<text class="chart-label year-label" data-year="{year}" x="{x_at(index):.1f}" '
            f'y="{height - 8}" text-anchor="{anchor}" fill="#93a4b8" font-size="{font}">{year}</text>'
        )
    chosen = list(callouts or [])
    if years[peak_index] not in chosen:
        chosen.append(years[peak_index])
    if not callouts:
        chosen = [years[0], years[values.index(min(values))], years[peak_index], years[-1]]
    specs = []
    seen = set()
    for year in chosen:
        if year not in years or year in seen:
            continue
        seen.add(year)
        index = years.index(year)
        specs.append(
            {
                "index": index,
                "year": year,
                "text": y_format(values[index]),
                "peak": index == peak_index,
            }
        )
    _layout_callouts(
        specs,
        points,
        font=font,
        frame=(4, 4, width - 4, top + plot_h - 2),
        gutter=left,
    )
    for spec in specs:
        peak_attr = ' data-peak="1"' if spec["peak"] else ""
        parts.append(
            f'<text class="chart-label callout" data-year="{spec["year"]}"{peak_attr} '
            f'x="{spec["x"]:.1f}" y="{spec["y"]:.1f}" text-anchor="{spec["anchor"]}" '
            f'fill="#f4f7fb" font-size="{font}">{_esc(spec["text"])}</text>'
        )
    parts.append("</svg>")
    return _wrap("".join(parts))


def spark(
    rows: Sequence[dict],
    *,
    chart_id: str,
    width: int = 720,
    height: int = 240,
    y_format=None,
    blocked: tuple[int, int] | None = None,
    font: int = 26,
) -> str:
    if len(rows) < 2:
        return "<p>Not enough months to draw this chart.</p>"
    y_format = y_format or (lambda value: f"{value:.0f}")
    values = [float(row["aud"]) for row in rows]
    left = max(72, int(_ink(y_format(max(values) or 1), font) + 16))
    right, top, bottom = 18, 28, 32
    plot_w = width - left - right
    plot_h = height - top - bottom
    ticks = _nice_ticks(values, include_zero=True, headroom=0.16)
    low, high = ticks[0], ticks[-1]
    span = high - low or 1.0

    def x_at(index: int) -> float:
        return left + plot_w * index / (len(rows) - 1)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - (value - low) / span)

    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    if blocked:
        _append_month_band(parts, rows, blocked, x_at, top, plot_h, font)
    for tick in ticks:
        y = y_at(tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="#2c3c4e"></line>'
        )
        parts.append(
            f'<text class="chart-label tick" x="{left - 10}" y="{y - font * 0.08:.1f}" '
            f'text-anchor="end" fill="#93a4b8" font-size="{font}">{_esc(y_format(tick))}</text>'
        )
    parts.append(
        f'<polyline fill="none" stroke="#6cb6ff" stroke-width="2.4" points="{points}"></polyline>'
    )
    for index in (0, len(rows) - 1):
        year = str(rows[index]["period"])[:4]
        parts.append(
            f'<text class="chart-label year-label" data-year="{year}" x="{x_at(index):.1f}" '
            f'y="{height - 8}" text-anchor="{"start" if index == 0 else "end"}" '
            f'fill="#93a4b8" font-size="{font}">{_esc(rows[index]["period"])}</text>'
        )
    parts.append("</svg>")
    return _wrap("".join(parts))


def annual_compare(
    rows: Sequence[dict],
    *,
    chart_id: str,
    width: int = 720,
    height: int = 340,
    y_format=None,
    blocked: tuple[int, int] | None = None,
    font: int = 26,
    show_values: bool = False,
) -> str:
    """Bars for recorded sales, with the zero-sale gap marked when there is one."""
    if not rows:
        return "<p>No figures for this chart.</p>"
    y_format = y_format or (lambda value: f"{value:.0f}")
    values = [float(row["actual"]) for row in rows]
    left = max(64, int(_ink(y_format(max(values) or 1), font) + 16))
    right, top, bottom = 14, int(font + 18), int(font + 20)
    plot_w = width - left - right
    plot_h = height - top - bottom
    ticks = _nice_ticks([0.0, *values], include_zero=True, headroom=0.18)
    low, high = min(0.0, ticks[0]), ticks[-1]
    span = high - low or 1.0
    slot = plot_w / len(rows)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - (value - low) / span)

    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
    ]
    years = [int(row["year"]) for row in rows]
    blocked_box = None
    if blocked and blocked[0] in years and blocked[1] in years:
        start, end = years.index(blocked[0]), years.index(blocked[1])
        x0 = left + slot * start
        x1 = left + slot * (end + 1)
        parts.append(
            f'<rect data-blocked="1" x="{x0:.1f}" y="{top}" width="{x1 - x0:.1f}" '
            f'height="{plot_h:.1f}" fill="#ff6b6b" opacity="0.18"></rect>'
        )
        label_x = (x0 + x1) / 2
        label_y = top + font + 2
        parts.append(
            f'<text class="chart-label blocked" x="{label_x:.1f}" y="{label_y:.1f}" '
            f'text-anchor="middle" fill="#ffd0d0" font-size="{font}">blocked</text>'
        )
        blocked_box = _text_box(label_x, label_y, "blocked", "middle", font)
    value_boxes: list[tuple[float, float, float, float]] = []
    if blocked_box:
        value_boxes.append(_widen(blocked_box, font * 0.2))
    for tick in ticks:
        if tick < low - 1e-9 or tick > high + 1e-9:
            continue
        y = y_at(tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="#2c3c4e"></line>'
        )
        parts.append(
            f'<text class="chart-label tick" x="{left - 10}" y="{y - font * 0.08:.1f}" '
            f'text-anchor="end" fill="#93a4b8" font-size="{font}">{_esc(y_format(tick))}</text>'
        )
        value_boxes.append(_text_box(left - 10, y - font * 0.08, y_format(tick), "end", font))
    base = y_at(0)
    for index, row in enumerate(rows):
        actual = float(row["actual"])
        x = left + slot * index + slot * 0.22
        bar_w = slot * 0.56
        y = y_at(actual)
        parts.append(
            f'<rect x="{x:.1f}" y="{min(y, base):.1f}" width="{bar_w:.1f}" '
            f'height="{abs(base - y):.1f}" rx="2" fill="#2ee6c7"></rect>'
        )
        if show_values and actual > 0:
            label = y_format(actual)
            lx = x + bar_w / 2
            ly = y - 6
            box = _text_box(lx, ly, label, "middle", font, factor=0.9)
            if box[1] < top + 2:
                ly = min(y + font, base - 4)
                box = _text_box(lx, ly, label, "middle", font, factor=0.9)
            wide = box
            clear = wide[1] >= 2 and wide[3] <= height - bottom
            clear = clear and not any(_boxes_overlap(wide, other, gap=3) for other in value_boxes)
            if clear:
                value_boxes.append(wide)
                parts.append(
                    f'<text class="chart-label" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                    f'fill="#f4f7fb" font-size="{font}">{_esc(label)}</text>'
                )
        year = int(row["year"])
        if index % 2 == 0 or index == len(rows) - 1:
            parts.append(
                f'<text class="chart-label year-label" data-year="{year}" '
                f'x="{left + slot * index + slot / 2:.1f}" y="{height - 8}" text-anchor="middle" '
                f'fill="#93a4b8" font-size="{font}">{year}</text>'
            )
    parts.append("</svg>")
    return _wrap("".join(parts))


def australia_map(
    features: Sequence[dict],
    values: dict[str, float],
    *,
    chart_id: str,
    missing: set[str] | None = None,
) -> str:
    missing = set(missing or [])
    projected = [_project_feature(feature) for feature in features]
    xs = [x for feature in projected for x, _y in feature["points"]]
    ys = [y for feature in projected for _x, y in feature["points"]]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width, height = 700, 620
    pad_x, pad_top, pad_bottom = 36, 28, 78
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    scale = min((width - 2 * pad_x) / span_x, (height - pad_top - pad_bottom) / span_y)

    def sx(x: float) -> float:
        return pad_x + (x - min_x) * scale

    def sy(y: float) -> float:
        return pad_top + (max_y - y) * scale

    states = []
    for feature in projected:
        rings = [[(sx(x), sy(y)) for x, y in ring] for ring in feature["rings"]]
        points = [point for ring in rings for point in ring]
        states.append(
            {
                "name": feature["name"],
                "short": _STATE_SHORT[feature["name"]],
                "rings": rings,
                "centroid": (sx(feature["centroid"][0]), sy(feature["centroid"][1])),
                "bbox": (
                    min(x for x, _y in points),
                    min(y for _x, y in points),
                    max(x for x, _y in points),
                    max(y for _x, y in points),
                ),
                "area": sum(abs(_shoelace(ring)) for ring in rings),
                "missing": feature["name"] in missing,
            }
        )
    labels = _place_state_labels(states, width, height)
    parts = [
        f'<svg class="chart" data-chart="{_esc(chart_id)}" viewBox="0 0 {width} {height}" '
        f'role="img" width="100%">'
        '<defs><pattern id="no-data-hatch" patternUnits="userSpaceOnUse" width="7" height="7" '
        'patternTransform="rotate(45)"><rect width="7" height="7" fill="#6a7684"/>'
        '<line x1="0" y1="0" x2="0" y2="7" stroke="#d5dde6" stroke-width="2"/></pattern></defs>'
    ]
    for state in states:
        if state["missing"]:
            colour = "url(#no-data-hatch)"
        else:
            colour = _share_colour(values.get(state["name"], 0.0))
        for ring in state["rings"]:
            coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in ring)
            parts.append(
                f'<polygon data-state="{state["short"]}" points="{coords}" fill="{colour}" '
                f'stroke="#0e141b" stroke-width="1.2"></polygon>'
            )
    for state in states:
        label = labels[state["short"]]
        if label["leader"]:
            (x1, y1), (x2, y2) = label["leader"]
            parts.append(
                f'<line class="leader" data-state="{state["short"]}" x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" stroke="#d5e2ef" stroke-width="1.3"></line>'
            )
    for state in states:
        label = labels[state["short"]]
        parts.append(
            f'<text class="chart-label" data-state="{state["short"]}" x="{label["x"]:.1f}" '
            f'y="{label["y"]:.1f}" text-anchor="{label["anchor"]}" fill="#f7fbff" '
            f'font-size="{_MAP_FONT}" font-weight="700">{state["short"]}</text>'
        )
    parts.append("</svg>")
    return _wrap("".join(parts))


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
_MAP_FONT = 26


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


def _nice_step(span: float, target: int) -> float:
    raw = span / max(target, 1)
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    for multiplier in (1, 2, 2.5, 5, 10):
        if residual <= multiplier + 1e-9:
            return multiplier * magnitude
    return 10 * magnitude


def _nice_ticks(
    values: Sequence[float],
    *,
    include_zero: bool = False,
    headroom: float = 0.12,
    target: int = 4,
) -> list[float]:
    raw_low = min(values)
    raw_high = max(values)
    if include_zero:
        raw_low = min(0.0, raw_low)
        raw_high = max(0.0, raw_high)
    span = raw_high - raw_low
    if span <= 0:
        span = abs(raw_high) or 1.0
        raw_low -= span / 2
        raw_high += span / 2
    else:
        raw_high += span * headroom
        if not include_zero:
            raw_low -= span * headroom * 0.55
    step = _nice_step(raw_high - raw_low, target)
    start = math.floor(raw_low / step + 1e-9) * step
    end = math.ceil((raw_high - 1e-9) / step) * step
    if end <= max(values) + step * 0.01:
        end += step
    count = max(int(round((end - start) / step)), 1)
    ticks = [round(start + index * step, 10) for index in range(count + 1)]
    cleaned = [ticks[0]]
    for tick in ticks[1:]:
        if abs(tick - cleaned[-1]) > step * 0.01:
            cleaned.append(tick)
    return cleaned


def _widen(box: tuple[float, float, float, float], pad: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return (left - pad, top, right + pad, bottom)


def _text_box(
    x: float, y: float, text: object, anchor: str, font: float, factor: float = 0.62
) -> tuple[float, float, float, float]:
    width = max(len(str(text)), 1) * font * factor
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    top = y - font * 0.82
    return (left, top, left + width, top + font)


def _boxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    gap: float = 0,
) -> bool:
    return not (
        a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1]
    )


def _segments_intersect(
    x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
) -> bool:
    def cross(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    d1 = cross(x3, y3, x4, y4, x1, y1)
    d2 = cross(x3, y3, x4, y4, x2, y2)
    d3 = cross(x1, y1, x2, y2, x3, y3)
    d4 = cross(x1, y1, x2, y2, x4, y4)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    )


def _segment_hits_rect(
    x1: float, y1: float, x2: float, y2: float, rect: tuple[float, float, float, float]
) -> bool:
    left, top, right, bottom = rect

    def inside(x: float, y: float) -> bool:
        return left <= x <= right and top <= y <= bottom

    if inside(x1, y1) or inside(x2, y2):
        return True
    edges = (
        (left, top, right, top),
        (right, top, right, bottom),
        (right, bottom, left, bottom),
        (left, bottom, left, top),
    )
    return any(_segments_intersect(x1, y1, x2, y2, *edge) for edge in edges)


def _box_hits_segments(
    box: tuple[float, float, float, float],
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    pad: float = 0,
) -> bool:
    left, top, right, bottom = box
    rect = (left - pad, top - pad, right + pad, bottom + pad)
    return any(_segment_hits_rect(x1, y1, x2, y2, rect) for (x1, y1), (x2, y2) in segments)


def _point_in_ring(x: float, y: float, ring: Sequence[tuple[float, float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=False):
        if (y1 > y) != (y2 > y):
            cross_x = (y - y1) * (x2 - x1) / (y2 - y1 + 1e-15) + x1
            if x < cross_x:
                inside = not inside
    return inside


def _layout_callouts(
    specs: list[dict],
    points: Sequence[tuple[float, float]],
    *,
    font: float,
    frame: tuple[float, float, float, float],
    gutter: float,
) -> None:
    segments = list(zip(points, points[1:], strict=False))
    order = sorted(
        range(len(specs)),
        key=lambda index: (not specs[index]["peak"], points[specs[index]["index"]][1]),
    )
    placed: list[tuple[float, float, float, float]] = []
    left, top, right, bottom = frame
    for index in order:
        spec = specs[index]
        px, py = points[spec["index"]]
        chosen = None
        for anchor, x, y in _callout_spots(spec, points, font):
            box = _text_box(x, y, spec["text"], anchor, font)
            if box[0] < left or box[1] < top or box[2] > right or box[3] > bottom:
                continue
            if box[0] < gutter - 2:
                continue
            if _box_hits_segments(box, segments, pad=3):
                continue
            if any(_boxes_overlap(box, other, gap=4) for other in placed):
                continue
            chosen = (x, y, anchor, box)
            break
        if chosen is None:
            y = min(bottom - font, py + font * 1.15)
            box = _text_box(px, y, spec["text"], "middle", font)
            chosen = (px, y, "middle", box)
        placed.append(chosen[3])
        spec["x"], spec["y"], spec["anchor"] = chosen[0], chosen[1], chosen[2]


def _callout_spots(spec: dict, points: Sequence[tuple[float, float]], font: float):
    """Try just above the point, then just under a dip where the valley is narrow."""
    index = spec["index"]
    px, py = points[index]
    above = []
    if spec["peak"]:
        above.append(("middle", px, py - font * 0.95))
    above.append(("middle", px, py - font * 0.85))
    above.append(("end", px - 10, py - font * 0.85))
    above.append(("start", px + 10, py - font * 0.85))
    for step in range(1, 5):
        lift = font * (0.85 + step * 0.32)
        above.append(("middle", px, py - lift))
        above.append(("end", px - 10, py - lift))
        above.append(("start", px + 10, py - lift))
    below = []
    for step in range(4):
        drop = font * (1.05 + step * 0.28)
        below.append(("middle", px, py + drop))
        below.append(("end", px - 8, py + drop))
        below.append(("start", px + 8, py + drop))
    # Peaks stay above the marker. Dips often only have room underneath.
    if spec["peak"]:
        return above
    return above[:4] + below + above[4:]


def _append_month_band(parts: list[str], rows, blocked, x_at, top, plot_h, font) -> None:
    start, end = blocked
    indexes = [
        index for index, row in enumerate(rows) if start <= int(str(row["period"])[:4]) <= end
    ]
    if not indexes:
        return
    x0 = x_at(indexes[0])
    x1 = x_at(indexes[-1])
    if x1 < x0:
        x0, x1 = x1, x0
    pad = 6
    parts.append(
        f'<rect data-blocked="1" x="{x0 - pad:.1f}" y="{top}" width="{x1 - x0 + 2 * pad:.1f}" '
        f'height="{plot_h:.1f}" fill="#ff6b6b" opacity="0.16"></rect>'
    )
    parts.append(
        f'<text class="chart-label blocked" x="{(x0 + x1) / 2:.1f}" y="{top + font:.1f}" '
        f'text-anchor="middle" fill="#ffd0d0" font-size="{font}">blocked</text>'
    )


def _place_state_labels(states: list[dict], width: float, height: float) -> dict[str, dict]:
    rings = [ring for state in states for ring in state["rings"]]
    east = max(state["bbox"][2] for state in states)
    placed: list[dict] = []
    found: dict[str, dict] = {}
    for state in sorted(states, key=lambda item: item["area"], reverse=True):
        label = _place_one_label(state, placed, rings, width, height, east)
        placed.append(label)
        found[state["short"]] = label
    return found


def _place_one_label(state, placed, rings, width, height, east) -> dict:
    font = _MAP_FONT
    text = state["short"]
    ring = max(state["rings"], key=lambda item: abs(_shoelace(item)))
    cx, cy = state["centroid"]
    min_x, min_y, max_x, max_y = state["bbox"]
    own_segments = _ring_segments(state["rings"])
    all_segments = _ring_segments(rings)

    def padded(x: float, y: float, anchor: str) -> tuple[float, float, float, float]:
        # Bold labels are wider than the regular ink estimate.
        return _text_box(x, y, text, anchor, font, factor=0.9)

    def samples(box: tuple[float, float, float, float]):
        left, top, right, bottom = box
        return (
            (left, top),
            (right, top),
            (left, bottom),
            (right, bottom),
            ((left + right) / 2, (top + bottom) / 2),
        )

    def on_land(box: tuple[float, float, float, float]) -> bool:
        return any(_point_in_ring(x, y, piece) for piece in rings for x, y in samples(box))

    def acceptable(box: tuple[float, float, float, float], *, inside: bool) -> bool:
        if box[0] < 6 or box[1] < 6 or box[2] > width - 6 or box[3] > height - 6:
            return False
        if any(_boxes_overlap(box, other["box"], gap=4) for other in placed):
            return False
        if inside:
            if _box_hits_segments(box, own_segments, pad=1):
                return False
            return all(_point_in_ring(x, y, ring) for x, y in samples(box))
        if _box_hits_segments(box, all_segments, pad=3):
            return False
        return not on_land(box)

    def chosen(x: float, y: float, anchor: str, box, leader) -> dict:
        return {"x": x, "y": y, "anchor": anchor, "box": box, "leader": leader}

    if text not in {"Tas", "ACT"}:
        best = None
        y = min_y + 4
        while y <= max_y:
            x = min_x + 4
            while x <= max_x:
                box = padded(x, y, "middle")
                if acceptable(box, inside=True):
                    dist = (x - cx) ** 2 + (y - cy) ** 2
                    if best is None or dist < best[0]:
                        best = (dist, x, y, box)
                x += 6
            y += 6
        if best is not None:
            return chosen(best[1], best[2], "middle", best[3], None)

    external: list[tuple[float, float, str]] = []
    if text == "Tas":
        mid = (min_x + max_x) / 2
        for extra in (18, 30, 44, 58):
            external.append((mid, max_y + font + extra, "middle"))
        external.append((max_x + 12, max_y + font + 10, "start"))
    if text == "ACT":
        for dy in (-48, -24, 0, 28, 52):
            external.append((east + 28, cy + dy, "start"))
            external.append((east + 28, min_y + dy, "start"))
    external.extend(
        (
            ((min_x + max_x) / 2, max_y + font + 24, "middle"),
            (east + 20, cy, "start"),
            (min_x - 12, cy, "end"),
            ((min_x + max_x) / 2, min_y - 14, "middle"),
        )
    )
    for x, y, anchor in external:
        box = padded(x, y, anchor)
        if acceptable(box, inside=False):
            return chosen(x, y, anchor, box, ((cx, cy), _edge_point(box, (cx, cy))))
    fallback_x = min(max(cx, 40), width - 40)
    fallback_y = min(height - 14, max(16, cy))
    box = padded(fallback_x, fallback_y, "middle")
    return chosen(fallback_x, fallback_y, "middle", box, ((cx, cy), _edge_point(box, (cx, cy))))


def _ring_segments(rings):
    segments = []
    for ring in rings:
        segments.extend(zip(ring, ring[1:] + ring[:1], strict=False))
    return segments


def _edge_point(box, target) -> tuple[float, float]:
    left, top, right, bottom = box
    tx, ty = target
    cx, cy = (left + right) / 2, (top + bottom) / 2
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return cx, top
    scale_x = (right - left) / 2 / abs(dx) if dx else 1e9
    scale_y = (bottom - top) / 2 / abs(dy) if dy else 1e9
    scale = min(scale_x, scale_y)
    return cx + dx * scale, cy + dy * scale
