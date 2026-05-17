import pandas as pd

from model_engine import (
    DEFAULT_ASSUMPTIONS,
    build_dcf_model,
    compute_tiered_royalty,
    royalty_tiers_from_assumptions,
)
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions


def test_tiered_royalty_calculation():
    assumptions = dict(DEFAULT_ASSUMPTIONS)
    assumptions.update({
        "royalty_tier_1_rate": 5.0,
        "royalty_tier_2_rate": 7.0,
        "royalty_tier_3_rate": 9.0,
        "royalty_tier_1_threshold": 100.0,
        "royalty_tier_2_threshold": 200.0,
    })
    tiers = royalty_tiers_from_assumptions(assumptions)

    # 5% on first 100, 7% on next 100, 9% on next 50 = 16.5
    assert compute_tiered_royalty(250.0, tiers) == 16.5


def test_dcf_model_returns_core_outputs():
    model = build_dcf_model(dict(DEFAULT_ASSUMPTIONS), {})
    summary = model["summary"]

    assert "rnpv" in summary
    assert "licensee_npv" in summary
    assert "licensor_npv" in summary
    assert "approval_probability" in summary
    assert len(model["years"]) == DEFAULT_ASSUMPTIONS["forecast_years"]


def test_validation_clips_impossible_percentages():
    assumptions = dict(DEFAULT_ASSUMPTIONS)
    assumptions["phase_i_success"] = 150.0
    assumptions["tax_rate"] = -10.0

    clean = validate_simulation_assumptions(assumptions)

    assert clean["phase_i_success"] == 100.0
    assert clean["tax_rate"] == 0.0


def test_monte_carlo_returns_expected_columns():
    df = run_biotech_monte_carlo(dict(DEFAULT_ASSUMPTIONS), n_sims=20, seed=1)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 20
    assert {"rnpv", "licensee_npv", "licensor_npv", "launch_year"}.issubset(df.columns)
