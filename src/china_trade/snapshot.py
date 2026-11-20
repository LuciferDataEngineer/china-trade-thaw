"""Download public ABS, RBA and Natural Earth files into a small parquet snapshot.

The briefing is rebuilt from this snapshot. CI does not call the live sources.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import openpyxl

from china_trade.catalog import (
    ABS_FLOW,
    ABS_RELEASE,
    ABS_STRUCTURE,
    FOCUS_SITC,
    NATURAL_EARTH,
    RBA_FX,
    RBA_FX_RECENT,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
RAW = ROOT / "data" / "raw"
MELBOURNE = ZoneInfo("Australia/Melbourne")
UA = "china-trade-thaw/1.0 (research; public ABS and RBA tables)"


def main() -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    accessed = datetime.now(MELBOURNE)
    sources: list[dict] = []

    print("ABS codelists", flush=True)
    structure = fetch(ABS_STRUCTURE, sources, "ABS MERCH_EXP structure")
    labels = parse_labels(structure)
    write_rows(
        SNAPSHOT / "labels.parquet",
        labels,
        ["dimension", "code", "name"],
    )

    print("ABS merchandise extracts", flush=True)
    frames: list[Path] = []
    queries = {
        "commodity_china": (".CHIN.TOT.M", "2006-01"),
        "commodity_world": (".TOT.TOT.M", "2006-01"),
        "partner_total": ("TOT..TOT.M", "2006-01"),
        "state_partner": ("TOT..1+2+3+4+5+6+7+8.M", "2015-01"),
    }
    for name, (key, start) in queries.items():
        path = RAW / f"{name}.csv"
        download_abs(key, start, path, sources, name)
        frames.append(path)
    for sitc in FOCUS_SITC:
        path = RAW / f"focus_{sitc}.csv"
        download_abs(f"{sitc}..TOT.M", "2006-01", path, sources, f"focus {sitc}")
        frames.append(path)
        path_state = RAW / f"focus_state_{sitc}.csv"
        download_abs(
            f"{sitc}.CHIN+TOT.1+2+3+4+5+6+7+8.M",
            "2015-01",
            path_state,
            sources,
            f"focus state {sitc}",
        )
        frames.append(path_state)

    merch_count = csvs_to_parquet(frames, SNAPSHOT / "merch_month.parquet")
    print(f"merch rows {merch_count}", flush=True)

    print("ABS country vintages", flush=True)
    vintage_rows: list[dict] = []
    for vintage, url in ABS_RELEASE.items():
        blob = fetch(url, sources, f"ABS table 14a {vintage}")
        xlsx_path = RAW / f"table14a_{vintage}.xlsx"
        xlsx_path.write_bytes(blob)
        vintage_rows.extend(parse_country_workbook(blob, vintage, url))
    write_rows(
        SNAPSHOT / "country_vintage.parquet",
        vintage_rows,
        ["vintage", "release_url", "country_name", "period", "aud_million"],
    )
    print(f"vintage rows {len(vintage_rows)}", flush=True)

    print("RBA exchange rates", flush=True)
    fx_rows = []
    for url, label in ((RBA_FX, "RBA F11"), (RBA_FX_RECENT, "RBA F11.1")):
        blob = fetch(url, sources, label)
        fx_rows.extend(parse_rba(blob))
    fx_rows = dedupe_fx(fx_rows)
    write_rows(SNAPSHOT / "fx_daily.parquet", fx_rows, ["date", "aud_usd", "aud_cny"])
    print(f"fx days {len(fx_rows)}", flush=True)

    print("Natural Earth states", flush=True)
    geo = fetch(NATURAL_EARTH, sources, "Natural Earth admin 1")
    states = filter_australia(geo)
    geo_path = SNAPSHOT / "au_states.geojson"
    geo_path.write_text(json.dumps(states), encoding="utf-8")

    manifest = {
        "project": "china-trade-thaw",
        "accessed_at": accessed.isoformat(timespec="seconds"),
        "accessed_at_melbourne": accessed.strftime("%-d %B %Y, %-I:%M %p %Z"),
        "note": (
            "CI rebuilds from these parquet and GeoJSON files. "
            "It does not call ABS, the RBA or Natural Earth."
        ),
        "sources": sources,
        "files": file_records(
            [
                SNAPSHOT / "merch_month.parquet",
                SNAPSHOT / "country_vintage.parquet",
                SNAPSHOT / "fx_daily.parquet",
                SNAPSHOT / "labels.parquet",
                geo_path,
            ]
        ),
        "row_counts": {
            "merch_month": merch_count,
            "country_vintage": len(vintage_rows),
            "fx_daily": len(fx_rows),
            "labels": len(labels),
            "au_states": len(states["features"]),
        },
    }
    (SNAPSHOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("snapshot ready", SNAPSHOT, flush=True)


def fetch(url: str, sources: list[dict], label: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                blob = response.read()
                status = response.status
            digest = hashlib.sha256(blob).hexdigest()
            sources.append(
                {
                    "label": label,
                    "url": url,
                    "http_status": status,
                    "bytes": len(blob),
                    "sha256": digest,
                }
            )
            print(f"  {label}: {len(blob)} bytes", flush=True)
            return blob
        except urllib.error.HTTPError as exc:
            body = exc.read()[:200]
            if exc.code == 404 and b"NoRecordsFound" in body:
                sources.append(
                    {
                        "label": label,
                        "url": url,
                        "http_status": 404,
                        "bytes": 0,
                        "sha256": None,
                        "note": "ABS returned no published observations for this slice",
                    }
                )
                print(f"  {label}: no records", flush=True)
                return b""
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - retry network failures
            last_error = exc
        time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def download_abs(key: str, start: str, path: Path, sources: list[dict], label: str) -> None:
    url = f"{ABS_FLOW}{key}?startPeriod={start}&format=csv"
    blob = fetch(url, sources, label)
    path.write_bytes(blob)


def csvs_to_parquet(paths: list[Path], dest: Path) -> int:
    usable = [str(path) for path in paths if path.stat().st_size > 0]
    if not usable:
        raise RuntimeError("ABS extracts were empty")
    con = duckdb.connect()
    listed = ", ".join("'" + path.replace("'", "''") + "'" for path in usable)
    con.execute(
        f"""
        COPY (
            SELECT
                COMMODITY_SITC AS commodity,
                COUNTRY_DEST AS country,
                STATE_ORIGIN AS state,
                CAST(TIME_PERIOD || '-01' AS DATE) AS period,
                CAST(OBS_VALUE AS DOUBLE) * pow(10, CAST(UNIT_MULT AS INTEGER)) AS aud,
                COALESCE(OBS_STATUS, '') AS obs_status
            FROM read_csv([{listed}], header = true, union_by_name = true)
            WHERE OBS_VALUE IS NOT NULL
              AND UNIT_MEASURE = 'AUD'
              AND (
                    COMMODITY_SITC = 'TOT'
                    OR regexp_matches(COMMODITY_SITC, '^[0-9]{{3}}$')
                  )
            QUALIFY row_number() OVER (
                PARTITION BY COMMODITY_SITC, COUNTRY_DEST, STATE_ORIGIN, TIME_PERIOD
                ORDER BY OBS_VALUE DESC
            ) = 1
        ) TO '{dest}' (FORMAT PARQUET)
        """
    )
    count = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
    con.close()
    if count < 1000:
        raise RuntimeError(f"merchandise extract looks too small: {count} rows")
    return int(count)


def parse_labels(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    wanted = {
        "CL_MERCH_SITC": "commodity",
        "CL_MERCH_COUNTRY": "country",
        "CL_MERCH_STATE": "state",
    }
    rows: list[dict] = []
    for codelist in root.iter():
        if not codelist.tag.endswith("Codelist"):
            continue
        dimension = wanted.get(codelist.attrib.get("id", ""))
        if dimension is None:
            continue
        for code in codelist:
            if not code.tag.endswith("Code"):
                continue
            name = ""
            for child in code.iter():
                if child.tag.endswith("Name") and child.text:
                    name = child.text
                    break
            rows.append(
                {
                    "dimension": dimension,
                    "code": code.attrib["id"],
                    "name": name.replace("&amp;", "&"),
                }
            )
    if len(rows) < 100:
        raise RuntimeError("ABS codelist parse failed")
    return rows


def parse_country_workbook(blob: bytes, vintage: str, url: str) -> list[dict]:
    if not blob:
        raise RuntimeError(f"empty workbook for {vintage}")
    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows: list[dict] = []
    for sheet_name in ("Data1", "Data2"):
        sheet = workbook[sheet_name]
        header = next(sheet.iter_rows(max_row=1, values_only=True))
        names = [clean_country(value) for value in header]
        for raw in sheet.iter_rows(min_row=11, values_only=True):
            period = raw[0]
            if not isinstance(period, datetime):
                continue
            if period.date() < date(2024, 1, 1):
                continue
            for index, name in enumerate(names):
                if index == 0 or not name:
                    continue
                value = raw[index] if index < len(raw) else None
                if value is None:
                    continue
                rows.append(
                    {
                        "vintage": vintage,
                        "release_url": url,
                        "country_name": name,
                        "period": period.date().isoformat(),
                        "aud_million": float(value),
                    }
                )
    workbook.close()
    if len(rows) < 1000:
        raise RuntimeError(f"workbook {vintage} parsed to only {len(rows)} rows")
    return rows


def clean_country(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s*;\s*$", "", str(value)).strip()


def parse_rba(blob: bytes) -> list[dict]:
    text = blob.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    rows: list[dict] = []
    for record in reader:
        if not record:
            continue
        if record[0] == "Title":
            header = record
            continue
        if header is None or not re.match(r"\d{2}-[A-Za-z]{3}-\d{4}$", record[0]):
            continue
        usd_at = _col(header, "A$1=USD")
        cny_at = _col(header, "A$1=CNY")
        if usd_at is None:
            continue
        when = datetime.strptime(record[0], "%d-%b-%Y").date()
        if when < date(2006, 1, 1):
            continue
        usd = _float(record, usd_at)
        cny = _float(record, cny_at) if cny_at is not None else None
        if usd is None:
            continue
        rows.append({"date": when.isoformat(), "aud_usd": usd, "aud_cny": cny})
    return rows


def _col(header: list[str], name: str) -> int | None:
    for index, value in enumerate(header):
        if value.strip() == name:
            return index
    return None


def _float(record: list[str], index: int) -> float | None:
    if index >= len(record) or record[index] in ("", "na", "NA"):
        return None
    try:
        return float(record[index])
    except ValueError:
        return None


def dedupe_fx(rows: list[dict]) -> list[dict]:
    by_date: dict[str, dict] = {}
    for row in rows:
        current = by_date.get(row["date"])
        if current is None:
            by_date[row["date"]] = row
            continue
        # The later file wins where it has a value, so F11.1 can extend F11.
        if row["aud_usd"] is not None:
            current["aud_usd"] = row["aud_usd"]
        if row["aud_cny"] is not None:
            current["aud_cny"] = row["aud_cny"]
    return [by_date[key] for key in sorted(by_date)]


def filter_australia(blob: bytes) -> dict:
    payload = json.loads(blob)
    features = []
    for feature in payload["features"]:
        props = feature.get("properties") or {}
        admin = props.get("admin") or props.get("adm0_name")
        name = props.get("name") or ""
        if admin != "Australia" or name == "Jervis Bay Territory":
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": props.get("name"),
                    "postal": props.get("postal"),
                    "iso_3166_2": props.get("iso_3166_2"),
                },
                "geometry": round_geometry(feature["geometry"]),
            }
        )
    if len(features) < 6:
        raise RuntimeError(f"expected Australian states, found {len(features)}")
    return {"type": "FeatureCollection", "features": features}


def round_geometry(geometry: dict) -> dict:
    kind = geometry["type"]
    if kind == "Polygon":
        return {"type": kind, "coordinates": round_rings(geometry["coordinates"])}
    if kind == "MultiPolygon":
        return {
            "type": kind,
            "coordinates": [round_rings(poly) for poly in geometry["coordinates"]],
        }
    raise RuntimeError(f"unsupported geometry {kind}")


def round_rings(rings: list) -> list:
    return [[[round(x, 3), round(y, 3)] for x, y in ring] for ring in rings]


def write_rows(path: Path, rows: list[dict], columns: list[str]) -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (SELECT 1) WHERE FALSE")
    # Build via pandas-free insertion through a relation.
    import pyarrow as pa

    arrays = []
    for column in columns:
        values = [row[column] for row in rows]
        arrays.append(pa.array(values))
    table = pa.Table.from_arrays(arrays, names=columns)
    con.register("incoming", table)
    con.execute(f"COPY incoming TO '{path}' (FORMAT PARQUET)")
    con.close()


def file_records(paths: list[Path]) -> list[dict]:
    records = []
    for path in paths:
        blob = path.read_bytes()
        records.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    return records


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
