"""Optional FastAPI layer for external valuation calls.

Run locally with:
    uvicorn api:api --reload

This does not replace the Dash app. It exposes the same engine for future Excel,
backend, or integration workflows.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from model_engine import DEFAULT_ASSUMPTIONS, build_dcf_model
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions


api = FastAPI(title="Biotech NPV Valuation API", version="0.1.0")


class ValuationRequest(BaseModel):
    assumptions: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_ASSUMPTIONS))
    overrides: dict[str, Any] = Field(default_factory=dict)


class MonteCarloRequest(ValuationRequest):
    n_sims: int = Field(default=1000, ge=10, le=10000)
    seed: int = 42


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/valuation")
def valuation(payload: ValuationRequest) -> dict[str, Any]:
    assumptions = validate_simulation_assumptions(payload.assumptions)
    model = build_dcf_model(assumptions, payload.overrides)
    return {
        "assumptions": assumptions,
        "summary": model["summary"],
        "years": model["years"],
    }


@api.post("/monte-carlo")
def monte_carlo(payload: MonteCarloRequest) -> dict[str, Any]:
    assumptions = validate_simulation_assumptions(payload.assumptions)
    df = run_biotech_monte_carlo(
        assumptions,
        overrides=payload.overrides,
        n_sims=payload.n_sims,
        seed=payload.seed,
    )
    rnpv = df["rnpv"]
    return {
        "n_sims": len(df),
        "mean_rnpv": float(rnpv.mean()),
        "median_rnpv": float(rnpv.median()),
        "p10_rnpv": float(rnpv.quantile(0.10)),
        "p90_rnpv": float(rnpv.quantile(0.90)),
        "probability_positive_rnpv": float(rnpv.gt(0).mean()),
    }
