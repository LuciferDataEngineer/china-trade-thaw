"""Bayesian synthetic control for the goods China restricted.

Each blocked good is compared with a weighted basket of China-bound goods that
were not restricted: iron ore, wool, milk and fruit. Weights come from a
Dirichlet prior, so they stay positive and sum to one. Donors are rescaled to
the blocked good's own pre-restriction level, because a weighted average of
iron ore cannot otherwise sit on the same scale as barley.

Wool is also run as a placebo, as if it had been restricted in 2020. It was
not. A large wool "loss" would mean the basket is inventing gaps.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence

import duckdb
import numpy as np
import pandas as pd

from china_trade.catalog import DONORS, PLACEBO_NAME, PLACEBO_SITC, RESTRICTED
from china_trade.metrics import scale_donors

DRAWS = 200
TUNE = 200
SEED = 18
HDI = 0.90


def fit_all(con: duckdb.DuckDBPyConnection) -> list[dict]:
    annual = _annual_frame(con)
    results = []
    for sitc, meta in RESTRICTED.items():
        results.append(
            _fit_one(
                annual,
                sitc=sitc,
                plain=meta["plain"],
                treat=meta["treat"],
                lift=meta["lift"],
                kind="restricted",
                donors=list(DONORS),
            )
        )
    results.append(
        _fit_one(
            annual,
            sitc=PLACEBO_SITC,
            plain=PLACEBO_NAME,
            treat=2020,
            lift=2023,
            kind="placebo",
            donors=[code for code in DONORS if code != PLACEBO_SITC],
        )
    )
    _write(con, results)
    return results


def _annual_frame(con: duckdb.DuckDBPyConnection) -> dict[str, dict[int, float]]:
    restricted = con.execute(
        """
        SELECT sitc, year, aud
        FROM gold.china_goods_year
        WHERE year BETWEEN 2006 AND 2025
        """
    ).fetchall()
    donors = con.execute(
        """
        SELECT sitc, year, aud
        FROM gold.donor_year
        WHERE year BETWEEN 2006 AND 2025
        """
    ).fetchall()
    frame: dict[str, dict[int, float]] = {}
    for sitc, year, aud in [*restricted, *donors]:
        frame.setdefault(sitc, {})[int(year)] = float(aud)
    years = list(range(2006, 2026))
    for sitc, series in frame.items():
        for year in years:
            series.setdefault(year, 0.0)
    return frame


def _fit_one(
    annual: dict[str, dict[int, float]],
    sitc: str,
    plain: str,
    treat: int,
    lift: int,
    kind: str,
    donors: Sequence[str],
) -> dict:
    import causalpy as cp

    pre_years = [year for year in range(2006, treat)]
    scaled, kept = scale_donors(annual, sitc, donors, pre_years)
    years = list(range(2006, 2026))
    columns = {sitc: [scaled[sitc][year] for year in years]}
    for donor in kept:
        columns[donor] = [scaled[donor][year] for year in years]
    data = pd.DataFrame(columns, index=years)
    notes: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = cp.SyntheticControl(
            data,
            treat,
            control_units=list(kept),
            treated_units=[sitc],
            model=cp.pymc_models.WeightedSumFitter(
                sample_kwargs={
                    "draws": DRAWS,
                    "tune": TUNE,
                    "chains": 2,
                    "cores": 1,
                    "random_seed": SEED,
                    "progressbar": False,
                    "target_accept": 0.9,
                }
            ),
        )
        for item in caught:
            text = str(item.message)
            if "Convex hull" in text or "correlation" in text:
                notes.append(text.split(".")[0])
    plot = result.get_plot_data(hdi_prob=HDI, treated_unit=sitc)
    ban_years = [year for year in years if treat <= year < lift]
    impact = result.post_impact.sel(treated_units=sitc, obs_ind=ban_years)
    loss_draws = -impact.sum(dim="obs_ind").values.reshape(-1)
    weights = _weights(result, kept)
    pre = plot.loc[plot.index < treat]
    pre_actual = pre[sitc].to_numpy(dtype=float)
    pre_pred = pre["prediction"].to_numpy(dtype=float)
    pre_mape = float(np.mean(np.abs(pre_actual - pre_pred)) / max(np.mean(pre_actual), 1.0))
    rows = []
    for year, row in plot.iterrows():
        low_col = f"pred_hdi_lower_{int(HDI * 100)}"
        high_col = f"pred_hdi_upper_{int(HDI * 100)}"
        rows.append(
            {
                "sitc": sitc,
                "year": int(year),
                "actual": float(row[sitc]),
                "prediction": float(row["prediction"]),
                "low": float(row[low_col]),
                "high": float(row[high_col]),
            }
        )
    return {
        "sitc": sitc,
        "plain": plain,
        "kind": kind,
        "treat_year": treat,
        "lift_year": lift,
        "pre_mape": pre_mape,
        "lost_aud": float(np.mean(loss_draws)),
        "lost_low": float(np.quantile(loss_draws, 0.05)),
        "lost_high": float(np.quantile(loss_draws, 0.95)),
        "weights": weights,
        "notes": notes,
        "years": rows,
        "donors": kept,
    }


def _weights(result: object, donors: Sequence[str]) -> dict[str, float]:
    beta = result.idata.posterior["beta"]
    # dims: chain, draw, treated_units, coeffs
    mean = beta.mean(dim=("chain", "draw"))
    values = np.asarray(mean.values).reshape(-1)
    labels = [str(value) for value in beta.coords["coeffs"].values]
    if len(labels) != len(values):
        labels = list(donors)
    return {label: float(value) for label, value in zip(labels, values, strict=False)}


def _write(con: duckdb.DuckDBPyConnection, results: list[dict]) -> None:
    goods = []
    years = []
    for result in results:
        goods.append(
            {
                "sitc": result["sitc"],
                "plain": result["plain"],
                "kind": result["kind"],
                "treat_year": result["treat_year"],
                "lift_year": result["lift_year"],
                "pre_mape": result["pre_mape"],
                "lost_aud": result["lost_aud"],
                "lost_low": result["lost_low"],
                "lost_high": result["lost_high"],
                "weights_json": json.dumps(result["weights"]),
                "notes": " ".join(result["notes"]),
            }
        )
        years.extend(result["years"])
    goods_df = pd.DataFrame(goods)
    years_df = pd.DataFrame(years)
    con.register("model_goods_df", goods_df)
    con.register("model_years_df", years_df)
    con.execute("CREATE TABLE gold.model_good AS SELECT * FROM model_goods_df")
    con.execute("CREATE TABLE gold.model_year AS SELECT * FROM model_years_df")
