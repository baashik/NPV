"""Additional valuation helpers for advanced biotech finance analysis.

These functions are intentionally standalone. They do not change the core DCF
until the methodology is reviewed and explicitly wired into the dashboard.
"""

from __future__ import annotations

from math import erf, exp, log, sqrt


def gordon_growth_terminal_value(final_year_fcf: float, discount_rate: float, perpetual_growth: float) -> float:
    """Calculate terminal value using the Gordon Growth method.

    Parameters are decimals, not percentages. Example: 12% = 0.12.
    """
    if discount_rate <= perpetual_growth:
        raise ValueError("Discount rate must be greater than perpetual growth rate.")
    return final_year_fcf * (1.0 + perpetual_growth) / (discount_rate - perpetual_growth)


def exit_multiple_terminal_value(metric: float, exit_multiple: float) -> float:
    """Calculate terminal value using an exit multiple.

    Metric can be revenue, EBITDA, or another selected valuation base.
    """
    if exit_multiple < 0:
        raise ValueError("Exit multiple cannot be negative.")
    return metric * exit_multiple


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def black_scholes_call_value(underlying_value: float, exercise_cost: float, time_years: float,
                             risk_free_rate: float, volatility: float) -> float:
    """Value a simple expansion option using Black-Scholes call logic.

    This can approximate an option to expand after positive clinical data, where
    the underlying value is the expanded commercial opportunity and the exercise
    cost is the incremental investment required.
    """
    if underlying_value <= 0 or exercise_cost <= 0:
        return 0.0
    if time_years <= 0:
        return max(underlying_value - exercise_cost, 0.0)
    if volatility <= 0:
        return max(underlying_value - exercise_cost * exp(-risk_free_rate * time_years), 0.0)

    d1 = (log(underlying_value / exercise_cost) + (risk_free_rate + 0.5 * volatility ** 2) * time_years) / (volatility * sqrt(time_years))
    d2 = d1 - volatility * sqrt(time_years)
    return underlying_value * _normal_cdf(d1) - exercise_cost * exp(-risk_free_rate * time_years) * _normal_cdf(d2)


def abandonment_option_value(expected_continuation_value: float, abandonment_recovery_value: float,
                             probability_abandon: float) -> float:
    """Simple expected-value proxy for an option to abandon.

    This is not a full binomial lattice. It gives a transparent first-pass view
    of downside protection from stopping a programme after poor results.
    """
    probability_abandon = min(max(probability_abandon, 0.0), 1.0)
    continue_probability = 1.0 - probability_abandon
    return continue_probability * expected_continuation_value + probability_abandon * abandonment_recovery_value
