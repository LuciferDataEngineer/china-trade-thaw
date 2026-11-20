"""Pure calculations for shares, concentration and the 10 percent shock."""

from __future__ import annotations

from collections.abc import Sequence


def shares(values: Sequence[float]) -> list[float]:
    """Turn non-negative values into shares of their sum."""
    cleaned = [float(v) for v in values]
    if any(v < 0 for v in cleaned):
        raise ValueError("shares need non-negative values")
    total = sum(cleaned)
    if total <= 0:
        raise ValueError("shares need a positive total")
    return [v / total for v in cleaned]


def hhi(partner_shares: Sequence[float]) -> float:
    """Herfindahl-Hirschman index. 1 means one buyer. 1/n means equal buyers."""
    weights = [float(s) for s in partner_shares]
    if any(s < 0 for s in weights):
        raise ValueError("HHI shares cannot be negative")
    total = sum(weights)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"HHI shares must sum to 1, got {total}")
    return sum(s * s for s in weights)


def top_share(partner_shares: Sequence[float], n: int = 1) -> float:
    if n < 1:
        raise ValueError("n must be at least 1")
    ordered = sorted((float(s) for s in partner_shares), reverse=True)
    return sum(ordered[:n])


def shock_value(china_aud: float, rate: float = 0.10) -> float:
    """Export income at stake if sales to China fall by ``rate``."""
    if rate < 0 or rate > 1:
        raise ValueError("shock rate must be between 0 and 1")
    if china_aud < 0:
        raise ValueError("China sales cannot be negative")
    return china_aud * rate


def scale_donors(
    rows: dict[str, dict[int, float]],
    treated: str,
    donors: Sequence[str],
    pre_years: Sequence[int],
) -> tuple[dict[str, dict[int, float]], list[str]]:
    """Put each donor on the treated good's pre-period level.

    A weighted average only lines up with barley or wine if iron ore and gold
    are rescaled to that good's own pre-period average. The treated series is
    left in Australian dollars. Donors with no pre-period sales are dropped.
    """
    pre = list(pre_years)
    treated_level = _mean([rows[treated][year] for year in pre])
    if treated_level <= 0:
        raise ValueError(f"{treated} has no pre-period sales")
    scaled = {treated: dict(rows[treated])}
    kept: list[str] = []
    for donor in donors:
        level = _mean([rows[donor][year] for year in pre])
        if level <= 0:
            continue
        factor = treated_level / level
        scaled[donor] = {year: value * factor for year, value in rows[donor].items()}
        kept.append(donor)
    if len(kept) < 2:
        raise ValueError("need at least two donors with pre-period sales")
    return scaled, kept


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(float(v) for v in values) / len(values)


def aud_text(value: float) -> str:
    """Stakeholder formatting. Negatives keep the sign."""
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:.1f} billion"
    if amount >= 10_000_000:
        return f"{sign}${amount / 1_000_000:.0f} million"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f} million"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:.0f} thousand"
    return f"{sign}${amount:.0f}"


def pct_text(share: float) -> str:
    return f"{share * 100:.0f}%"


def pct_text_1(share: float) -> str:
    return f"{share * 100:.1f}%"
