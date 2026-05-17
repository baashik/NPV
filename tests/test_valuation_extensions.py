import math

import pytest

from valuation_extensions import (
    abandonment_option_value,
    black_scholes_call_value,
    exit_multiple_terminal_value,
    gordon_growth_terminal_value,
)


def test_gordon_growth_terminal_value():
    tv = gordon_growth_terminal_value(final_year_fcf=100.0, discount_rate=0.12, perpetual_growth=0.03)
    assert tv == pytest.approx(1144.4444, rel=1e-4)


def test_gordon_growth_requires_discount_above_growth():
    with pytest.raises(ValueError):
        gordon_growth_terminal_value(final_year_fcf=100.0, discount_rate=0.03, perpetual_growth=0.03)


def test_exit_multiple_terminal_value():
    assert exit_multiple_terminal_value(metric=50.0, exit_multiple=8.0) == 400.0


def test_black_scholes_call_value_is_positive():
    value = black_scholes_call_value(
        underlying_value=100.0,
        exercise_cost=80.0,
        time_years=2.0,
        risk_free_rate=0.03,
        volatility=0.40,
    )
    assert math.isfinite(value)
    assert value > 0


def test_abandonment_option_value():
    value = abandonment_option_value(
        expected_continuation_value=-20.0,
        abandonment_recovery_value=5.0,
        probability_abandon=0.60,
    )
    assert value == pytest.approx(-5.0)
