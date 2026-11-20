import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = ("index.html", "recovery.html", "states.html", "grow.html")

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def site_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=SITE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.4)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_pages_render_without_overlap(browser, site_url, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    try:
        for name in PAGES:
            page.goto(f"{site_url}/{name}", wait_until="networkidle")
            assert page.locator("svg.chart").count() >= 1
            assert page.locator("h1").count() == 1
            _assert_labels(page)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 2"
            )
            assert overflow, name
        page.goto(f"{site_url}/recovery.html", wait_until="networkidle")
        page.click("button[data-panel='321']")
        assert page.locator("[data-panel-id='321']").is_visible()
        assert page.locator("[data-panel-id='043']").is_hidden()
        years = page.locator("svg[data-chart='china-share'] text.year-label")
        # China share chart is on the exposure page.
        page.goto(f"{site_url}/index.html", wait_until="networkidle")
        years = page.locator("svg[data-chart='china-share'] text.year-label")
        pairs = []
        for index in range(years.count()):
            item = years.nth(index)
            box = item.bounding_box()
            pairs.append((int(item.get_attribute("data-year")), box["x"]))
        assert [year for year, _x in pairs] == sorted(year for year, _x in pairs)
        assert [x for _year, x in pairs] == sorted(x for _year, x in pairs)
    finally:
        context.close()
    assert errors == [], errors


def _assert_labels(page):
    problems = page.evaluate(
        """
        () => {
          const issues = [];
          const overlaps = (a, b) => !(
            a.right <= b.left + 1 || b.right <= a.left + 1 ||
            a.bottom <= b.top + 1 || b.bottom <= a.top + 1
          );
          const hidden = [...document.querySelectorAll("[hidden]")];
          hidden.forEach((node) => { node.hidden = false; });
          try {
            for (const svg of document.querySelectorAll("svg.chart")) {
              const frame = svg.getBoundingClientRect();
              const labels = [...svg.querySelectorAll("text.chart-label")]
                .filter((node) => node.getClientRects().length > 0)
                .map((node) => node.getBoundingClientRect());
              labels.forEach((box) => {
                if (box.left < frame.left - 3 || box.top < frame.top - 3 ||
                    box.right > frame.right + 3 || box.bottom > frame.bottom + 3) {
                  issues.push("cut off " + svg.getAttribute("data-chart"));
                }
              });
              for (let i = 0; i < labels.length; i++) {
                for (let j = i + 1; j < labels.length; j++) {
                  if (overlaps(labels[i], labels[j])) {
                    issues.push("overlap " + svg.getAttribute("data-chart"));
                  }
                }
              }
            }
          } finally {
            hidden.forEach((node) => { node.hidden = true; });
          }
          return issues;
        }
        """
    )
    assert problems == [], problems


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_kpi_values_stay_on_one_line(browser, site_url, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    try:
        for name in PAGES:
            page.goto(f"{site_url}/{name}", wait_until="networkidle")
            problems = page.evaluate(
                """
                () => {
                  const issues = [];
                  const values = [...document.querySelectorAll(".kpi-value")];
                  values.forEach((node) => {
                    if (node.getClientRects().length !== 1) {
                      issues.push("wraps " + node.textContent);
                    }
                    const value = node.getBoundingClientRect();
                    const card = node.closest(".kpi").getBoundingClientRect();
                    if (value.left < card.left - 1 || value.right > card.right + 1) {
                      issues.push("overflow " + node.textContent);
                    }
                  });
                  const rows = new Map();
                  document.querySelectorAll(".kpi").forEach((card) => {
                    const box = card.getBoundingClientRect();
                    const key = Math.round(box.top / 4);
                    if (!rows.has(key)) rows.set(key, []);
                    rows.get(key).push(box.height);
                  });
                  rows.forEach((heights) => {
                    if (Math.max(...heights) - Math.min(...heights) > 1.5) {
                      issues.push("unequal kpi row");
                    }
                  });
                  return issues;
                }
                """
            )
            assert problems == [], (name, problems)
    finally:
        context.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_chart_text_is_at_least_11px(browser, site_url, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    try:
        for name in PAGES:
            page.goto(f"{site_url}/{name}", wait_until="networkidle")
            problems = page.evaluate(
                """
                () => {
                  const hidden = [...document.querySelectorAll("[hidden]")];
                  hidden.forEach((node) => { node.hidden = false; });
                  const issues = [];
                  try {
                    document.querySelectorAll("svg.chart text").forEach((node) => {
                      const specified = parseFloat(node.getAttribute("font-size") || "0");
                      const ctm = node.getScreenCTM();
                      const rendered = ctm ? specified * Math.hypot(ctm.a, ctm.b) : 0;
                      if (rendered < 11) {
                        issues.push(
                          rendered.toFixed(2) + "px " + node.textContent.trim()
                          + " " + node.closest("svg").getAttribute("data-chart")
                        );
                      }
                    });
                  } finally {
                    hidden.forEach((node) => { node.hidden = true; });
                  }
                  return issues;
                }
                """
            )
            assert problems == [], (name, problems[:12])
    finally:
        context.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_map_labels_clear_boundaries(browser, site_url, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    try:
        page.goto(f"{site_url}/states.html", wait_until="networkidle")
        problems = page.evaluate(
            """
            () => {
              const issues = [];
              const svg = document.querySelector("svg[data-chart='state-map']");
              const legend = document.querySelector(".legend");
              const act = svg.querySelector("polygon[data-state='ACT']");
              if (!act || !act.getAttribute("fill").includes("no-data")) {
                issues.push("ACT is not marked no data");
              }
              if (!legend.textContent.includes("No data")) issues.push("legend missing no data");
              const tops = new Map();
              legend.querySelectorAll("li").forEach((item) => {
                const top = Math.round(item.getBoundingClientRect().top);
                tops.set(top, (tops.get(top) || 0) + 1);
              });
              if (tops.size > 1 && [...tops.values()].some((count) => count === 1)) {
                issues.push("legend item sits on a row alone");
              }
              const overlaps = (a, b) => !(
                a.right <= b.left + 1 || b.right <= a.left + 1 ||
                a.bottom <= b.top + 1 || b.bottom <= a.top + 1
              );
              const crosses = (x1, y1, x2, y2, x3, y3, x4, y4) => {
                const cross = (ax, ay, bx, by, cx, cy) => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
                const d1 = cross(x3, y3, x4, y4, x1, y1);
                const d2 = cross(x3, y3, x4, y4, x2, y2);
                const d3 = cross(x1, y1, x2, y2, x3, y3);
                const d4 = cross(x1, y1, x2, y2, x4, y4);
                return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
                  ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
              };
              const view = svg.viewBox.baseVal;
              const labels = [...svg.querySelectorAll("text.chart-label")].map((node) => {
                const x = parseFloat(node.getAttribute("x"));
                const y = parseFloat(node.getAttribute("y"));
                const font = parseFloat(node.getAttribute("font-size"));
                const anchor = node.getAttribute("text-anchor") || "start";
                const width = node.getComputedTextLength();
                let left = x;
                if (anchor === "middle") left = x - width / 2;
                if (anchor === "end") left = x - width;
                const box = {
                  name: node.getAttribute("data-state"),
                  left, top: y - font * 0.82, right: left + width, bottom: y + font * 0.2,
                };
                if (box.left < 1 || box.top < 1 || box.right > view.width - 1 || box.bottom > view.height - 1) {
                  issues.push("clipped " + box.name);
                }
                return box;
              });
              for (let i = 0; i < labels.length; i++) {
                for (let j = i + 1; j < labels.length; j++) {
                  if (overlaps(labels[i], labels[j])) {
                    issues.push("label overlap " + labels[i].name + " " + labels[j].name);
                  }
                }
              }
              const edges = [...svg.querySelectorAll("polygon")].flatMap((poly) => {
                const pts = poly.getAttribute("points").trim().split(/\\s+/).map((pair) => {
                  const [x, y] = pair.split(",").map(Number);
                  return {x, y};
                });
                const segs = [];
                for (let i = 0; i < pts.length; i++) {
                  const a = pts[i];
                  const b = pts[(i + 1) % pts.length];
                  segs.push([a.x, a.y, b.x, b.y]);
                }
                return segs;
              });
              labels.forEach((box) => {
                const sides = [
                  [box.left, box.top, box.right, box.top],
                  [box.right, box.top, box.right, box.bottom],
                  [box.right, box.bottom, box.left, box.bottom],
                  [box.left, box.bottom, box.left, box.top],
                ];
                const hit = edges.some((edge) => sides.some((side) => crosses(...side, ...edge)));
                if (hit) issues.push("boundary " + box.name);
              });
              const frame = svg.getBoundingClientRect();
              svg.querySelectorAll("text.chart-label").forEach((node) => {
                const box = node.getBoundingClientRect();
                if (box.left < frame.left - 2 || box.top < frame.top - 2 ||
                    box.right > frame.right + 2 || box.bottom > frame.bottom + 2) {
                  issues.push("screen clip " + node.getAttribute("data-state"));
                }
              });
              return issues;
            }
            """
        )
        assert problems == [], problems
    finally:
        context.close()


def test_bar_charts_are_sorted_where_intended(browser, site_url):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    try:
        for name in ("recovery.html", "grow.html"):
            page.goto(f"{site_url}/{name}", wait_until="networkidle")
            problems = page.evaluate(
                """
                () => {
                  const parseValue = (text) => {
                    const match = text.replace(/,/g, "").match(/-?\\d+(?:\\.\\d+)?/);
                    if (!match) return null;
                    let value = parseFloat(match[0]);
                    if (/bn|billion/.test(text)) value *= 1e9;
                    else if (/\\bm\\b|million/.test(text)) value *= 1e6;
                    return value;
                  };
                  const issues = [];
                  document.querySelectorAll("svg[data-sort='desc']").forEach((svg) => {
                    const values = [...svg.querySelectorAll("text.chart-label")]
                      .filter((node) => node.getAttribute("text-anchor") === "end")
                      .map((node) => parseValue(node.textContent));
                    for (let i = 1; i < values.length; i++) {
                      if (values[i] > values[i - 1] + 1e-6) {
                        issues.push(svg.getAttribute("data-chart") + " not descending");
                        break;
                      }
                    }
                  });
                  const coal = document.querySelector("svg[data-chart='buyers-321']");
                  if (coal) {
                    const first = coal.querySelector("text.chart-label").textContent;
                    if (first !== "Japan") issues.push("coal first is " + first);
                    const china = coal.querySelector("rect[data-code='CHIN']");
                    const fills = [...coal.querySelectorAll("rect[data-code]")]
                      .filter((node) => node !== china)
                      .map((node) => node.getAttribute("fill"));
                    if (!china || fills.includes(china.getAttribute("fill"))) {
                      issues.push("China is not a distinct colour");
                    }
                  }
                  const recovery = document.querySelector("svg[data-chart='recovery-ratio']");
                  if (recovery) {
                    const first = recovery.querySelector("text.chart-label").textContent;
                    if (first !== "Beef") issues.push("recovery first is " + first);
                  }
                  return issues;
                }
                """
            )
            assert problems == [], (name, problems)
        page.goto(f"{site_url}/recovery.html", wait_until="networkidle")
        barley = page.locator("[data-panel-id='043']").inner_text()
        assert "For Barley alone" in barley
        assert "$3.0 billion" in barley
        assert "every blocked group combined" in barley
        assert page.locator("svg[data-chart='annual-043'] [data-blocked]").count() >= 1
        assert page.locator("svg[data-chart='annual-043'] text.blocked").text_content() == "blocked"
        assert page.locator("svg[data-chart='annual-043'] text.tick").count() >= 2
        assert page.locator("svg[data-chart='month-043'] [data-blocked]").count() >= 1
        assert page.locator("svg[data-chart='month-043'] text.tick").count() >= 2
        assert page.locator(".kpi-value", has_text="$41.2bn").count() == 1
        card = page.locator(".kpi", has_text="$41.2bn").inner_text()
        assert "all eight blocked groups" in card
        page.goto(f"{site_url}/index.html", wait_until="networkidle")
        assert (
            page.locator(".kpi", has_text="Sales to China").locator(".kpi-value").inner_text()
            == "$191.9bn"
        )
        peak = page.locator("svg[data-chart='china-share'] text[data-peak='1']")
        assert peak.text_content() == "40.4%"
        assert peak.get_attribute("data-year") == "2020"
        placed = page.evaluate(
            """
            () => {
              const svg = document.querySelector("svg[data-chart='china-share']");
              const point = svg.querySelector("circle[data-peak-point]");
              const label = svg.querySelector("text[data-peak]");
              const poly = svg.querySelector("polyline").getAttribute("points").trim().split(/\\s+/)
                .map((pair) => pair.split(",").map(Number));
              const peak = poly.reduce((best, item) => item[1] < best[1] ? item : best, poly[0]);
              const crosses = (x1, y1, x2, y2, x3, y3, x4, y4) => {
                const cross = (ax, ay, bx, by, cx, cy) => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
                const d1 = cross(x3, y3, x4, y4, x1, y1);
                const d2 = cross(x3, y3, x4, y4, x2, y2);
                const d3 = cross(x1, y1, x2, y2, x3, y3);
                const d4 = cross(x1, y1, x2, y2, x4, y4);
                return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
                  ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
              };
              const hits = (node) => {
                const x = parseFloat(node.getAttribute("x"));
                const y = parseFloat(node.getAttribute("y"));
                const font = parseFloat(node.getAttribute("font-size"));
                const anchor = node.getAttribute("text-anchor") || "start";
                const width = node.getComputedTextLength();
                let left = x;
                if (anchor === "middle") left = x - width / 2;
                if (anchor === "end") left = x - width;
                const box = [left, y - font * 0.82, left + width, y + font * 0.18];
                const sides = [
                  [box[0], box[1], box[2], box[1]],
                  [box[2], box[1], box[2], box[3]],
                  [box[2], box[3], box[0], box[3]],
                  [box[0], box[3], box[0], box[1]],
                ];
                for (let i = 1; i < poly.length; i++) {
                  if (sides.some((side) => crosses(...side, poly[i - 1][0], poly[i - 1][1], poly[i][0], poly[i][1]))) {
                    return node.textContent;
                  }
                }
                return "";
              };
              const overlaps = [...svg.querySelectorAll("text.callout")].map(hits).filter(Boolean);
              const ticks = [...document.querySelectorAll("svg[data-chart='aud-usd'] text.tick")]
                .map((node) => node.textContent);
              return {
                dx: Math.abs(parseFloat(label.getAttribute("x")) - parseFloat(point.getAttribute("cx"))),
                above: parseFloat(label.getAttribute("y")) < parseFloat(point.getAttribute("cy")) - 4,
                onPeak: Math.abs(parseFloat(point.getAttribute("cx")) - peak[0]) < 0.2,
                overlaps,
                ticks,
              };
            }
            """
        )
        assert placed["onPeak"]
        assert placed["above"]
        assert placed["dx"] <= 36
        assert placed["overlaps"] == []
        assert placed["ticks"]
        assert all(len(tick.split(".")[-1]) == 2 for tick in placed["ticks"])
        assert "0.00" not in placed["ticks"]
        assert min(float(tick) for tick in placed["ticks"]) >= 0.60
        assert max(float(tick) for tick in placed["ticks"]) <= 1.20
    finally:
        context.close()
