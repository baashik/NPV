"""
NPV Model — Constants, precomputed arrays, and typed parameter container.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np

# ============================================================================
# Time axis
# ============================================================================
START_YEAR = 2026
END_YEAR = 2042
YEARS = list(range(START_YEAR, END_YEAR + 1))
N_YEARS = len(YEARS)
YEAR_INDEX = np.arange(N_YEARS)  # 0 … 16

# ============================================================================
# Precomputed static arrays  (never recomputed)
# ============================================================================
ADOPTION_SCHEDULE: Dict[int, float] = {
    0: 0.00, 1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00, 6: 0.00,
    7: 0.60, 8: 0.80, 9: 0.90, 10: 1.00, 11: 1.00, 12: 1.00,
    13: 0.70, 14: 0.40, 15: 0.20, 16: 0.20,
}
ADOPTION_ARRAY: np.ndarray = np.array(
    [ADOPTION_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)]
)

RD_SCHEDULE: Dict[int, float] = {0: 2.0, 1: 3.0, 2: 2.0, 3: 3.0, 4: 3.0, 5: 3.0, 6: 2.0}
RD_ARRAY: np.ndarray = np.array(
    [RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)]
)

ROYALTY_TIERS_DEFAULT: List[Tuple[float, float, float]] = [
    (0, 100, 0.050),
    (100, 200, 0.070),
    (200, float("inf"), 0.090),
]

# ============================================================================
# Design tokens
# ============================================================================
COLORS: Dict[str, str] = {
    "primary":      "#6750A4",
    "secondary":    "#625B71",
    "success":      "#2E7D32",
    "warning":      "#F57F17",
    "danger":       "#C62828",
    "info":         "#0288D1",
    "teal":         "#00838F",
    "bg":           "#FFFBFE",
    "card":         "#FFFFFF",
    "blue":         "#1565C0",
    "red":          "#C62828",
    "green":        "#2E7D32",
    "grey":         "#546E7A",
    "amber":        "#F57F17",
}

# ============================================================================
# Typed parameter container
# ============================================================================
@dataclass
class ScenarioParams:
    eu_pop:     float = 450.0
    ts:         float = 0.09        # target share
    dr:         float = 0.80        # diagnosis rate
    tr:         float = 0.50        # treatment rate
    cogs:       float = 0.12
    ga:         float = 0.01
    tax:        float = 0.21
    upfront:    float = 2.0
    p1:         float = 0.63
    p2:         float = 0.30
    p3:         float = 0.58
    p4:         float = 0.90
    peak_pen:   float = 0.05
    asset_discount_rate: float = 0.12  # Core DCF / standalone product rNPV
    licensee_wacc:         float = 0.10  # Licensee Model
    licensor_discount_rate: float = 0.14  # Licensor Model
    rd:         Dict[int, float] = field(default_factory=lambda: RD_SCHEDULE.copy())
    milestones: Dict[int, float] = field(default_factory=lambda: {2: 1.0, 4: 1.0, 6: 1.0})
    tiers:      List[Tuple[float, float, float]] = field(default_factory=lambda: ROYALTY_TIERS_DEFAULT.copy())


def build_params(
    pop: float, price: float, pen: float, cogs: float, tax: float,
    asset_dr: float, licensee_wacc: float, licensor_dr: float,
    p1: float, p2: float, p3: float, p4: float,
    upfront: float, mil: float,
) -> ScenarioParams:
    return ScenarioParams(
        eu_pop=float(pop or 450),
        cogs=float(cogs or 12) / 100,
        tax=float(tax or 21) / 100,
        upfront=float(upfront or 2),
        p1=float(p1 or 63) / 100,
        p2=float(p2 or 30) / 100,
        p3=float(p3 or 58) / 100,
        p4=float(p4 or 90) / 100,
        peak_pen=float(pen or 5) / 100,
        asset_discount_rate=float(asset_dr or 12) / 100,
        licensee_wacc=float(licensee_wacc or 10) / 100,
        licensor_discount_rate=float(licensor_dr or 14) / 100,
        milestones={2: float(mil or 1), 4: float(mil or 1), 6: float(mil or 1)},
    )
