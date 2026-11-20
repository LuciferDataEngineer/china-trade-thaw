import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from china_trade.metrics import aud_compact, hhi, scale_donors, shares, shock_value, top_share


def test_one_buyer_is_fully_concentrated():
    assert hhi([1.0]) == pytest.approx(1.0)


def test_equal_buyers():
    assert hhi([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.25)


def test_shock_is_a_tenth():
    assert shock_value(191.9e9, 0.10) == pytest.approx(19.19e9)


def test_compact_money_fits_a_kpi():
    assert aud_compact(191.9e9) == "$191.9bn"
    assert aud_compact(19.2e9) == "$19.2bn"
    assert aud_compact(173e6) == "$173m"
    assert aud_compact(1.5e6) == "$1.5m"


def test_scale_donors_matches_the_treated_level():
    rows = {
        "barley": {2018: 100.0, 2019: 300.0, 2020: 10.0},
        "wool": {2018: 50.0, 2019: 150.0, 2020: 80.0},
        "milk": {2018: 20.0, 2019: 20.0, 2020: 20.0},
    }
    scaled, kept = scale_donors(rows, "barley", ["wool", "milk"], [2018, 2019])
    treated_level = (100 + 300) / 2
    for donor in kept:
        level = (scaled[donor][2018] + scaled[donor][2019]) / 2
        assert level == pytest.approx(treated_level)
    assert scaled["barley"][2020] == 10.0


@settings(max_examples=40, derandomize=True)
@given(st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=1, max_size=12))
def test_hhi_is_between_equal_and_one(values):
    weights = shares(values)
    score = hhi(weights)
    floor = 1 / len(weights)
    assert floor - 1e-9 <= score <= 1 + 1e-9
    assert sum(weights) == pytest.approx(1.0)
    assert top_share(weights, 1) >= floor - 1e-9


def test_hhi_rejects_shares_that_do_not_add_up():
    with pytest.raises(ValueError):
        hhi([0.2, 0.2])
