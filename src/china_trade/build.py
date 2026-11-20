"""Rebuild the warehouse, the comparison and the briefing from the snapshot."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from china_trade.causal import fit_all
from china_trade.dashboard import render
from china_trade.graph import build_graph
from china_trade.insights import write as write_insights
from china_trade.quality import check_contract, check_frames
from china_trade.story import build_story
from china_trade.transform import assert_descriptive, build_descriptive, connect

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    con = connect()
    build_descriptive(con)
    assert_descriptive(con)
    check_frames(con)
    print("fitting the comparisons", flush=True)
    fit_all(con)
    graph = build_graph(con)
    story = build_story(con)
    check_contract(con)
    render(story)
    write_insights(story, graph)
    (ROOT / "data" / "story.json").write_text(json.dumps(_slim(story), indent=2), encoding="utf-8")
    print(story["exposure"]["headline"])
    print(story["recovery"]["headline"])
    print(story["states"]["headline"])
    print(story["grow"]["headline"])
    print("graph", graph["engine"])
    con.close()


def _slim(story: dict) -> dict:
    recovery = dict(story["recovery"])
    recovery["goods"] = [
        {key: value for key, value in good.items() if key not in {"monthly", "annual"}}
        for good in recovery["goods"]
    ]
    return {**story, "recovery": recovery}


if __name__ == "__main__":
    main()
