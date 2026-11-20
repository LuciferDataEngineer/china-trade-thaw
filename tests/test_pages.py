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
          return issues;
        }
        """
    )
    assert problems == [], problems
