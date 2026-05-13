"""
BIOPHARMA LICENSING DEAL — MONTE CARLO NPV SIMULATION
Drug: GATX-11 | Fibrosis | Phase I → EU Exclusive License
Licensor (Biotech) ↔ Licensee (Pharma Partner)

All blue-cell assumptions are collected at the top.
Change any value here and re-run — the full model recalculates.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

np.random.seed(42)

# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — ASSUMPTIONS  (all editable inputs)
# ══════════════════════════════════════════════════════════════════════════════

# ── Simulation control ────────────────────────────────────────────────────────
N_SIMULATIONS = 10_000
START_YEAR    = 2026
END_YEAR      = 2042
YEARS         = list(range(START_YEAR, END_YEAR + 1))
N_YEARS       = len(YEARS)

# ── Revenue model assumptions ─────────────────────────────────────────────────
EU_POPULATION_M          = 450       # M — base EU population
POP_GROWTH_RATE_MEAN     = 0.020     # annual growth (can go negative = decline)
POP_GROWTH_RATE_SD       = 0.04      # stochastic SD

TARGET_PATIENT_SHARE     = 0.09      # fraction of EU pop = target patients
DIAGNOSIS_RATE           = 0.80      # % diagnosed
TREATMENT_RATE           = 0.50      # % of diagnosed treated

PEAK_PENETRATION_MEAN    = 0.05      # peak market penetration %
PEAK_PENETRATION_SD      = 0.01      # stochastic SD
YEARS_TO_PEAK            = 5         # ramp years after launch (year 7)

PRICE_PER_UNIT_MEAN      = 100.0     # $ per patient/year
PRICE_PER_UNIT_SD        = 25.0      # stochastic SD

ANNUAL_PREVALENCE_GROWTH = 0.02      # annual patient growth rate

# ── Adoption schedule (relative to launch year = index 7 = 2033) ─────────────
# index 0-6 = pre-launch; index 7 onward = commercial
ADOPTION_SCHEDULE = {
    0:0.00, 1:0.00, 2:0.00, 3:0.00, 4:0.00, 5:0.00, 6:0.00,
    7:0.60, 8:0.80, 9:0.90, 10:1.00, 11:1.00, 12:1.00,
    13:0.70, 14:0.40, 15:0.20, 16:0.20
}

# ── Cost assumptions ─────────────────────────────────────────────────────────
COGS_PCT        = 0.12   # % of net revenue
GA_OPEX_PCT     = 0.01   # G&A as % of net revenue
TAX_RATE        = 0.21   # corporate tax
WORKING_CAPITAL = 0.15   # % of revenue per year

# R&D spend by year index (spread across phases):
#   Ph I: year 0-1 | Ph II: year 1-3 | Ph III: year 3-5 | Approval/Mktg: year 6
RD_SCHEDULE = {
    0: 2, 1: 3, 2: 2, 3: 3, 4: 3, 5: 3, 6: 2
}   # $M per year (reflects Ph I=4M, Ph II=5M, Ph III=7M, Approval+Mktg=2M)

# ── Discount rates ────────────────────────────────────────────────────────────
LICENSEE_WACC_MEAN  = 0.100;  LICENSEE_WACC_SD  = 0.025
LICENSOR_WACC_MEAN  = 0.140;  LICENSOR_WACC_SD  = 0.025
RISK_FREE_RATE      = 0.04

# ── Clinical success probabilities ────────────────────────────────────────────
P_PH1_PH2   = 0.300
P_PH2_PH3   = 0.490
P_PH3_NDA   = 0.553
P_NDA_APPROV= 0.950

# Cumulative probability of reaching market
P_SUCCESS = P_PH1_PH2 * P_PH2_PH3 * P_PH3_NDA * P_NDA_APPROV

# ── Deal terms ────────────────────────────────────────────────────────────────
UPFRONT_M         = 2.0
MILESTONES = {     # year_index: $M
    0: 1.0,  # Ph1 Start (upfront already separate, this = Ph1 start milestone)
    2: 1.0,  # Ph2 Start
    4: 1.0,  # Ph3 Start
    6: 2.0,  # NDA Filing + Approval combined
}

# Tiered royalty structure
ROYALTY_TIERS = [
    (0,   100,  0.050),   # 0–100M: 5%
    (100, 200,  0.070),   # 100–200M: 7%
    (200, np.inf, 0.090), # >200M: 9%
]

def compute_royalty(revenue_m):
    """Tiered royalty calculation."""
    royalty = 0.0
    for lo, hi, rate in ROYALTY_TIERS:
        if revenue_m > lo:
            royalty += min(revenue_m - lo, hi - lo) * rate
    return royalty


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — SINGLE SCENARIO ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def run_scenario(
    pop_growth=POP_GROWTH_RATE_MEAN,
    peak_penetration=PEAK_PENETRATION_MEAN,
    price=PRICE_PER_UNIT_MEAN,
    licensee_wacc=LICENSEE_WACC_MEAN,
    licensor_wacc=LICENSOR_WACC_MEAN,
):
    """
    Returns dict with full annual P&L, NPV metrics for both licensee & licensor.
    """
    revenue   = np.zeros(N_YEARS)
    fcf_full  = np.zeros(N_YEARS)   # licensee FCF (includes R&D)
    royalty   = np.zeros(N_YEARS)

    population = EU_POPULATION_M
    for i in range(N_YEARS):
        population *= (1 + pop_growth)
        adopt = ADOPTION_SCHEDULE.get(i, 0.0)
        penetration = peak_penetration * adopt

        treated = (population * TARGET_PATIENT_SHARE
                   * DIAGNOSIS_RATE * TREATMENT_RATE
                   * penetration)

        rev = treated * price
        revenue[i] = max(rev, 0)

    for i in range(N_YEARS):
        rev = revenue[i]
        cogs    = rev * COGS_PCT
        gross   = rev - cogs
        ga      = rev * GA_OPEX_PCT
        rd_cost = RD_SCHEDULE.get(i, 0.0)
        ebitda  = gross - ga - rd_cost

        # Tax with loss carry-forward
        cum_loss = sum(RD_SCHEDULE.get(j, 0.0) for j in range(i+1) if revenue[j] == 0)
        taxable  = max(ebitda - cum_loss, 0)
        tax      = taxable * TAX_RATE if ebitda > 0 else 0

        royalty[i] = compute_royalty(rev)
        fcf_full[i] = ebitda - tax - royalty[i]

    # ── PRTS risk adjustment ─────────────────────────────────────────────────
    cum_prob = np.ones(N_YEARS)
    cum = 1.0
    phase_probs = [1.0, P_PH1_PH2, 1.0, P_PH2_PH3, 1.0, P_PH3_NDA, P_NDA_APPROV]
    for i in range(N_YEARS):
        if i < len(phase_probs):
            cum *= phase_probs[i]
        cum_prob[i] = min(cum, 1.0)

    risk_adj_fcf = fcf_full * cum_prob

    # ── Discount factors ──────────────────────────────────────────────────────
    df_licensee = np.array([(1 / (1 + licensee_wacc))**i for i in range(N_YEARS)])
    df_licensor = np.array([(1 / (1 + licensor_wacc))**i for i in range(N_YEARS)])

    licensee_enpv = float(np.sum(risk_adj_fcf * df_licensee))

    # ── Licensor cash flows ───────────────────────────────────────────────────
    licensor_cf = np.zeros(N_YEARS)
    licensor_cf[0] += UPFRONT_M
    for yr_idx, mil_m in MILESTONES.items():
        if yr_idx < N_YEARS:
            licensor_cf[yr_idx] += mil_m

    risk_adj_royalty = royalty * cum_prob
    licensor_cf += risk_adj_royalty

    licensor_npv = float(np.sum(licensor_cf * df_licensor))

    return {
        "revenue":          revenue,
        "royalty":          royalty,
        "fcf":              fcf_full,
        "risk_adj_fcf":     risk_adj_fcf,
        "licensor_cf":      licensor_cf,
        "licensee_enpv":    licensee_enpv,
        "licensor_npv":     licensor_npv,
        "cum_prob":         cum_prob,
        "df_licensee":      df_licensee,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — MONTE CARLO SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

print(f"Running {N_SIMULATIONS:,} Monte Carlo simulations…")

licensee_npvs = np.zeros(N_SIMULATIONS)
licensor_npvs = np.zeros(N_SIMULATIONS)

# Store a few revenue paths for visualisation
rev_paths = []

for s in range(N_SIMULATIONS):
    pg    = np.random.normal(POP_GROWTH_RATE_MEAN, POP_GROWTH_RATE_SD)
    pp    = max(np.random.normal(PEAK_PENETRATION_MEAN, PEAK_PENETRATION_SD), 0.001)
    pr    = max(np.random.normal(PRICE_PER_UNIT_MEAN, PRICE_PER_UNIT_SD), 10)
    lsw   = max(np.random.normal(LICENSEE_WACC_MEAN, LICENSEE_WACC_SD), 0.05)
    lrw   = max(np.random.normal(LICENSOR_WACC_MEAN, LICENSOR_WACC_SD), 0.05)

    res = run_scenario(pg, pp, pr, lsw, lrw)
    licensee_npvs[s] = res["licensee_enpv"]
    licensor_npvs[s] = res["licensor_npv"]
    if s < 200:
        rev_paths.append(res["revenue"])

rev_paths = np.array(rev_paths)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — BASE CASE (for charts & summary)
# ══════════════════════════════════════════════════════════════════════════════

base = run_scenario()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

def mc_stats(arr, label):
    pct = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    prob_pos = np.mean(arr > 0)
    return {
        "label":    label,
        "mean":     np.mean(arr),
        "std":      np.std(arr),
        "min":      np.min(arr),
        "p5":       pct[0],
        "p10":      pct[1],
        "p25":      pct[2],
        "p50":      pct[3],
        "p75":      pct[4],
        "p90":      pct[5],
        "p95":      pct[6],
        "max":      np.max(arr),
        "prob_pos": prob_pos,
    }

ls_stats = mc_stats(licensee_npvs, "Licensee eNPV ($M)")
lr_stats = mc_stats(licensor_npvs, "Licensor Deal NPV ($M)")

print("\n" + "="*60)
print("  MONTE CARLO RESULTS SUMMARY")
print("="*60)
for st in [ls_stats, lr_stats]:
    print(f"\n  {st['label']}")
    print(f"    Mean:         ${st['mean']:>8.2f}M")
    print(f"    Std Dev:      ${st['std']:>8.2f}M")
    print(f"    P5  / P95:    ${st['p5']:>6.2f}M  /  ${st['p95']:>6.2f}M")
    print(f"    P25 / P75:    ${st['p25']:>6.2f}M  /  ${st['p75']:>6.2f}M")
    print(f"    Median (P50): ${st['p50']:>8.2f}M")
    print(f"    Max:          ${st['max']:>8.2f}M")
    print(f"    Prob(NPV > 0): {st['prob_pos']*100:.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — SENSITIVITY (tornado)
# ══════════════════════════════════════════════════════════════════════════════

def sens_npv(key, val):
    kwargs = dict(
        pop_growth=POP_GROWTH_RATE_MEAN,
        peak_penetration=PEAK_PENETRATION_MEAN,
        price=PRICE_PER_UNIT_MEAN,
        licensee_wacc=LICENSEE_WACC_MEAN,
        licensor_wacc=LICENSOR_WACC_MEAN,
    )
    kwargs[key] = val
    return run_scenario(**kwargs)["licensee_enpv"]

base_enpv = base["licensee_enpv"]

sensitivity = {
    "Peak Penetration":  (0.02, 0.10),
    "Price per Patient": (60,   150),
    "Ph2→Ph3 Success":   (0.30, 0.65),
    "Licensee WACC":     (0.07, 0.16),
    "Pop Growth Rate":   (-0.02, 0.05),
    "COGS %":            (0.07, 0.20),
    "Tax Rate":          (0.15, 0.28),
}
key_map = {
    "Peak Penetration":  "peak_penetration",
    "Price per Patient": "price",
    "Ph2→Ph3 Success":   "peak_penetration",   # proxy via separate path below
    "Licensee WACC":     "licensee_wacc",
    "Pop Growth Rate":   "pop_growth",
    "COGS %":            "peak_penetration",    # proxy
    "Tax Rate":          "peak_penetration",    # proxy
}

def sens_manual(label, low_val, high_val):
    """Direct parameter sensitivity."""
    mapping = {
        "Peak Penetration":  ("peak_penetration", low_val, high_val),
        "Price per Patient": ("price", low_val, high_val),
        "Licensee WACC":     ("licensee_wacc", low_val, high_val),
        "Pop Growth Rate":   ("pop_growth", low_val, high_val),
    }
    if label in mapping:
        k, lo, hi = mapping[label]
        return sens_npv(k, lo), sens_npv(k, hi)
    # Ph2→Ph3 not a direct param — scale peak_penetration as proxy
    if label == "Ph2→Ph3 Success":
        scale_lo = low_val  / P_PH2_PH3
        scale_hi = high_val / P_PH2_PH3
        lo = base_enpv * (P_PH1_PH2 * low_val  * P_PH3_NDA * P_NDA_APPROV) / P_SUCCESS
        hi = base_enpv * (P_PH1_PH2 * high_val * P_PH3_NDA * P_NDA_APPROV) / P_SUCCESS
        return lo, hi
    if label == "COGS %":
        # Vary COGS in isolated revenue scenario
        def cogs_npv(cogs):
            r = run_scenario()
            rev = r["revenue"]
            cum = r["cum_prob"]; df = r["df_licensee"]
            fcf = np.zeros(N_YEARS)
            for i in range(N_YEARS):
                rv = rev[i]
                fcf[i] = rv*(1-cogs-GA_OPEX_PCT) - RD_SCHEDULE.get(i,0) - compute_royalty(rv)
            return float(np.sum(fcf * cum * df))
        return cogs_npv(low_val), cogs_npv(high_val)
    if label == "Tax Rate":
        def tax_npv(tr):
            r = run_scenario()
            rev = r["revenue"]
            cum = r["cum_prob"]; df = r["df_licensee"]
            fcf = np.zeros(N_YEARS)
            for i in range(N_YEARS):
                rv = rev[i]
                ebitda = rv*(1-COGS_PCT-GA_OPEX_PCT) - RD_SCHEDULE.get(i,0)
                tax = max(ebitda,0)*tr
                fcf[i] = ebitda - tax - compute_royalty(rv)
            return float(np.sum(fcf * cum * df))
        return tax_npv(low_val), tax_npv(high_val)
    return base_enpv, base_enpv

tornado_rows = []
for label, (lo_v, hi_v) in sensitivity.items():
    npv_lo, npv_hi = sens_manual(label, lo_v, hi_v)
    tornado_rows.append({
        "label":   label,
        "low_val": lo_v, "high_val": hi_v,
        "npv_lo":  npv_lo, "npv_hi": npv_hi,
        "range":   abs(npv_hi - npv_lo),
    })
tornado_df = pd.DataFrame(tornado_rows).sort_values("range", ascending=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — FIGURES
# ══════════════════════════════════════════════════════════════════════════════

BLUE  = "#1565C0"
TEAL  = "#00838F"
AMBER = "#F57F17"
RED   = "#C62828"
GREY  = "#546E7A"
LGREY = "#ECEFF1"
WHITE = "#FFFFFF"

plt.rcParams.update({
    "font.family":  "DejaVu Sans",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.facecolor":    WHITE,
    "figure.facecolor":  WHITE,
    "font.size": 9,
})


# ────────────────────────────────────────────────────────────────────────────
#  FIG 1 — INVESTOR DASHBOARD  (2 × 3 grid)
# ────────────────────────────────────────────────────────────────────────────
fig1 = plt.figure(figsize=(18, 12))
fig1.suptitle(
    "GATX-11 · Fibrosis · EU Exclusive License — Monte Carlo NPV Dashboard",
    fontsize=14, fontweight="bold", y=0.98
)
gs = GridSpec(2, 3, figure=fig1, hspace=0.45, wspace=0.35)

# ── Panel A: Revenue Fan Chart ────────────────────────────────────────────────
ax_a = fig1.add_subplot(gs[0, 0])
pct5  = np.percentile(rev_paths, 5,  axis=0)
pct25 = np.percentile(rev_paths, 25, axis=0)
pct50 = np.percentile(rev_paths, 50, axis=0)
pct75 = np.percentile(rev_paths, 75, axis=0)
pct95 = np.percentile(rev_paths, 95, axis=0)

ax_a.fill_between(YEARS, pct5,  pct95, alpha=0.15, color=BLUE, label="P5–P95")
ax_a.fill_between(YEARS, pct25, pct75, alpha=0.30, color=BLUE, label="P25–P75")
ax_a.plot(YEARS, pct50, color=BLUE, lw=2, label="Median")
ax_a.plot(YEARS, base["revenue"], color=AMBER, lw=1.5, ls="--", label="Base Case")
ax_a.set_title("A. Revenue Forecast Fan Chart", fontweight="bold")
ax_a.set_ylabel("Revenue ($M)"); ax_a.set_xlabel("Year")
ax_a.legend(fontsize=7, frameon=False)
ax_a.tick_params(axis="x", rotation=45)

# ── Panel B: Licensee eNPV Distribution ──────────────────────────────────────
ax_b = fig1.add_subplot(gs[0, 1])
n, bins, patches = ax_b.hist(licensee_npvs, bins=80, color=BLUE, alpha=0.75, edgecolor="white", lw=0.3)
for patch, left in zip(patches, bins):
    if left < 0:
        patch.set_facecolor(RED)
ax_b.axvline(ls_stats["mean"],  color=AMBER,  lw=2, ls="--", label=f"Mean: ${ls_stats['mean']:.1f}M")
ax_b.axvline(ls_stats["p50"],   color=TEAL,   lw=2, ls=":",  label=f"P50: ${ls_stats['p50']:.1f}M")
ax_b.axvline(0, color="black", lw=1.2, alpha=0.6)
ax_b.set_title("B. Licensee eNPV Distribution", fontweight="bold")
ax_b.set_xlabel("eNPV ($M)"); ax_b.set_ylabel("Frequency")
ax_b.legend(fontsize=7, frameon=False)
ppos = ls_stats["prob_pos"]*100
ax_b.text(0.97, 0.93, f"P(NPV>0) = {ppos:.1f}%",
          transform=ax_b.transAxes, ha="right", fontsize=9,
          color=BLUE, fontweight="bold")

# ── Panel C: Licensor NPV Distribution ───────────────────────────────────────
ax_c = fig1.add_subplot(gs[0, 2])
n2, bins2, patches2 = ax_c.hist(licensor_npvs, bins=80, color=TEAL, alpha=0.75, edgecolor="white", lw=0.3)
for patch, left in zip(patches2, bins2):
    if left < 0:
        patch.set_facecolor(RED)
ax_c.axvline(lr_stats["mean"], color=AMBER, lw=2, ls="--", label=f"Mean: ${lr_stats['mean']:.1f}M")
ax_c.axvline(lr_stats["p50"],  color=BLUE,  lw=2, ls=":",  label=f"P50: ${lr_stats['p50']:.1f}M")
ax_c.axvline(0, color="black", lw=1.2, alpha=0.6)
ax_c.set_title("C. Licensor Deal NPV Distribution", fontweight="bold")
ax_c.set_xlabel("Deal NPV ($M)"); ax_c.set_ylabel("Frequency")
ax_c.legend(fontsize=7, frameon=False)
lr_ppos = lr_stats["prob_pos"]*100
ax_c.text(0.97, 0.93, f"P(NPV>0) = {lr_ppos:.1f}%",
          transform=ax_c.transAxes, ha="right", fontsize=9,
          color=TEAL, fontweight="bold")

# ── Panel D: Cumulative probability (S-curve) ─────────────────────────────────
ax_d = fig1.add_subplot(gs[1, 0])
sorted_ls = np.sort(licensee_npvs)
sorted_lr = np.sort(licensor_npvs)
cdf = np.arange(1, N_SIMULATIONS+1) / N_SIMULATIONS
ax_d.plot(sorted_ls, cdf, color=BLUE, lw=2, label="Licensee eNPV")
ax_d.plot(sorted_lr, cdf, color=TEAL, lw=2, label="Licensor NPV")
ax_d.axvline(0, color="black", lw=1, alpha=0.5, ls="--")
ax_d.axhline(0.5, color=GREY, lw=0.8, ls=":", alpha=0.7)
for p, c in [(0.05,"#E3F2FD"),(0.25,"#BBDEFB"),(0.75,"#BBDEFB"),(0.95,"#E3F2FD")]:
    ax_d.axhline(p, color=BLUE, lw=0.5, ls=":", alpha=0.4)
ax_d.set_title("D. Cumulative Probability (S-Curve)", fontweight="bold")
ax_d.set_xlabel("NPV ($M)"); ax_d.set_ylabel("Cumulative Probability")
ax_d.yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f"{y*100:.0f}%"))
ax_d.legend(fontsize=8, frameon=False)

# ── Panel E: Tornado Chart ────────────────────────────────────────────────────
ax_e = fig1.add_subplot(gs[1, 1])
y_pos = range(len(tornado_df))
for i, (_, row) in enumerate(tornado_df.iterrows()):
    lo = min(row["npv_lo"], row["npv_hi"]) - base_enpv
    hi = max(row["npv_lo"], row["npv_hi"]) - base_enpv
    ax_e.barh(i, hi, left=0, color=BLUE, alpha=0.8, height=0.6)
    ax_e.barh(i, lo, left=0, color=RED,  alpha=0.8, height=0.6)
ax_e.axvline(0, color="black", lw=1.2)
ax_e.set_yticks(list(y_pos))
ax_e.set_yticklabels(tornado_df["label"].tolist(), fontsize=8)
ax_e.set_title("E. Tornado Chart — eNPV Sensitivity", fontweight="bold")
ax_e.set_xlabel("Δ eNPV vs Base Case ($M)")
pos_patch = mpatches.Patch(color=BLUE, label="Upside", alpha=0.8)
neg_patch = mpatches.Patch(color=RED,  label="Downside", alpha=0.8)
ax_e.legend(handles=[pos_patch, neg_patch], fontsize=7, frameon=False)

# ── Panel F: Percentile Table ─────────────────────────────────────────────────
ax_f = fig1.add_subplot(gs[1, 2])
ax_f.axis("off")
table_data = [
    ["Metric", "Licensee eNPV", "Licensor NPV"],
    ["Mean",    f"${ls_stats['mean']:.1f}M",  f"${lr_stats['mean']:.1f}M"],
    ["Std Dev", f"${ls_stats['std']:.1f}M",   f"${lr_stats['std']:.1f}M"],
    ["P5",      f"${ls_stats['p5']:.1f}M",    f"${lr_stats['p5']:.1f}M"],
    ["P10",     f"${ls_stats['p10']:.1f}M",   f"${lr_stats['p10']:.1f}M"],
    ["P25",     f"${ls_stats['p25']:.1f}M",   f"${lr_stats['p25']:.1f}M"],
    ["P50 (Median)", f"${ls_stats['p50']:.1f}M", f"${lr_stats['p50']:.1f}M"],
    ["P75",     f"${ls_stats['p75']:.1f}M",   f"${lr_stats['p75']:.1f}M"],
    ["P90",     f"${ls_stats['p90']:.1f}M",   f"${lr_stats['p90']:.1f}M"],
    ["P95",     f"${ls_stats['p95']:.1f}M",   f"${lr_stats['p95']:.1f}M"],
    ["Max",     f"${ls_stats['max']:.1f}M",   f"${lr_stats['max']:.1f}M"],
    ["P(NPV>0)", f"{ls_stats['prob_pos']*100:.1f}%", f"{lr_stats['prob_pos']*100:.1f}%"],
]
tbl = ax_f.table(
    cellText=table_data[1:],
    colLabels=table_data[0],
    cellLoc="center", loc="center",
    bbox=[0, 0, 1, 1]
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(8)
for (r, c), cell in tbl.get_celld().items():
    if r == 0:
        cell.set_facecolor(BLUE); cell.set_text_props(color=WHITE, fontweight="bold")
    elif r % 2 == 0:
        cell.set_facecolor(LGREY)
    cell.set_edgecolor("white")
ax_f.set_title("F. Percentile Summary Table", fontweight="bold", pad=12)

fig1.savefig("/mnt/user-data/outputs/01_investor_dashboard.png", dpi=150, bbox_inches="tight")
print("Saved: 01_investor_dashboard.png")


# ────────────────────────────────────────────────────────────────────────────
#  FIG 2 — BASE CASE P&L + CASH FLOW WATERFALL
# ────────────────────────────────────────────────────────────────────────────
fig2, axes = plt.subplots(1, 2, figsize=(16, 6))
fig2.suptitle("Base Case — Revenue Model & Licensee Cash Flow Waterfall", fontweight="bold")

# Left: stacked bar — revenue, COGS, royalties, R&D
rev  = base["revenue"]
cogs_arr = rev * COGS_PCT
roys = base["royalty"]
rds  = np.array([RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)])
gross_after = rev - cogs_arr - roys - rds

ax2l = axes[0]
x = np.arange(N_YEARS)
ax2l.bar(x, rev,         color=BLUE,  alpha=0.9,  label="Gross Revenue")
ax2l.bar(x, -cogs_arr,   color=RED,   alpha=0.7,  label="COGS")
ax2l.bar(x, -roys,       color=AMBER, alpha=0.8,  label="Royalty Paid")
ax2l.bar(x, -rds,        color=GREY,  alpha=0.7,  label="R&D Spend")
ax2l.plot(x, gross_after, "o-", color=TEAL, lw=2, ms=4, label="Net FCF")
ax2l.axhline(0, color="black", lw=0.8)
ax2l.set_xticks(x); ax2l.set_xticklabels([str(y) for y in YEARS], rotation=45, fontsize=7)
ax2l.set_title("Revenue Bridge: Gross → Net FCF")
ax2l.set_ylabel("$M"); ax2l.legend(fontsize=7, frameon=False)

# Right: Discounted FCF waterfall
ax2r = axes[1]
disc_fcf = base["risk_adj_fcf"] * base["df_licensee"]
colors = [BLUE if v >= 0 else RED for v in disc_fcf]
ax2r.bar(x, disc_fcf, color=colors, alpha=0.85, edgecolor="white", lw=0.4)
ax2r.axhline(0, color="black", lw=0.8)
cumulative = np.cumsum(disc_fcf)
ax2r.plot(x, cumulative, "D--", color=AMBER, lw=1.8, ms=4, label=f"Cumulative eNPV")
ax2r.axhline(base_enpv, color=TEAL, lw=1.5, ls=":", label=f"Total eNPV ${base_enpv:.1f}M")
ax2r.set_xticks(x); ax2r.set_xticklabels([str(y) for y in YEARS], rotation=45, fontsize=7)
ax2r.set_title("Risk-Adjusted Discounted FCF (Licensee)")
ax2r.set_ylabel("$M"); ax2r.legend(fontsize=7, frameon=False)

fig2.tight_layout()
fig2.savefig("/mnt/user-data/outputs/02_base_case_cashflow.png", dpi=150, bbox_inches="tight")
print("Saved: 02_base_case_cashflow.png")


# ────────────────────────────────────────────────────────────────────────────
#  FIG 3 — LICENSOR VALUE BRIDGE
# ────────────────────────────────────────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(12, 5))
fig3.suptitle("Licensor Deal NPV — Value Bridge (Base Case)", fontweight="bold")

lc = base["licensor_cf"]
disc_lc = lc * np.array([(1/(1+LICENSOR_WACC_MEAN))**i for i in range(N_YEARS)])

components = {
    "Upfront\n($2M)":    disc_lc[0],
    "Milestones":        sum(disc_lc[i] for i in MILESTONES if i > 0 and i < N_YEARS),
    "Royalties\n(PV)":   sum(disc_lc[i] for i in range(N_YEARS) if base["royalty"][i] > 0),
}
cum, bars = 0, []
labels, vals = list(components.keys()), list(components.values())
for i, (lab, val) in enumerate(zip(labels, vals)):
    col = BLUE if val >= 0 else RED
    ax3.bar(i, val, bottom=cum, color=col, alpha=0.85, width=0.5, edgecolor="white")
    ax3.text(i, cum + val/2, f"${val:.2f}M", ha="center", va="center",
             fontsize=9, color=WHITE, fontweight="bold")
    cum += val

# Total bar
ax3.bar(len(labels), cum, color=TEAL, alpha=0.9, width=0.5, edgecolor="white")
ax3.text(len(labels), cum/2, f"${cum:.2f}M\nTotal NPV", ha="center", va="center",
         fontsize=9, color=WHITE, fontweight="bold")

ax3.axhline(0, color="black", lw=0.8)
ax3.set_xticks(range(len(labels)+1))
ax3.set_xticklabels(labels + ["Total\nDeal NPV"], fontsize=9)
ax3.set_ylabel("$M")
ax3.set_title("Components of Licensor Deal NPV (Discounted @ Licensor WACC)")
fig3.tight_layout()
fig3.savefig("/mnt/user-data/outputs/03_licensor_value_bridge.png", dpi=150, bbox_inches="tight")
print("Saved: 03_licensor_value_bridge.png")


# ────────────────────────────────────────────────────────────────────────────
#  FIG 4 — PROBABILITY ANALYSIS DEEP-DIVE
# ────────────────────────────────────────────────────────────────────────────
fig4, axes4 = plt.subplots(1, 3, figsize=(18, 5))
fig4.suptitle("Probability & Risk Analysis", fontweight="bold")

# Left: Phase success probability waterfall
ax4l = axes4[0]
phases = ["Ph1→Ph2", "Ph2→Ph3", "Ph3→NDA", "NDA→Approv", "Market"]
probs  = [P_PH1_PH2, P_PH2_PH3, P_PH3_NDA, P_NDA_APPROV, 1.0]
cum_p  = []
c = 1.0
for p in probs:
    c *= p
    cum_p.append(c)

ax4l.bar(phases, [p*100 for p in cum_p], color=BLUE, alpha=0.8, edgecolor="white")
ax4l.bar(phases, [(1-p)*100 for p in cum_p], bottom=[p*100 for p in cum_p],
         color=LGREY, edgecolor="white")
for i, (ph, cp) in enumerate(zip(phases, cum_p)):
    ax4l.text(i, cp*100/2, f"{cp*100:.1f}%", ha="center", va="center",
              color=WHITE, fontsize=9, fontweight="bold")
ax4l.set_ylabel("Cumulative P(Success) %")
ax4l.set_title("Cumulative Clinical\nSuccess Probability")
ax4l.set_ylim(0, 105)

# Middle: NPV by quartile box
ax4m = axes4[1]
bp = ax4m.boxplot(
    [licensee_npvs, licensor_npvs],
    labels=["Licensee\neNPV", "Licensor\nNPV"],
    patch_artist=True,
    medianprops=dict(color=AMBER, lw=2),
    whiskerprops=dict(color=GREY),
    capprops=dict(color=GREY),
    flierprops=dict(marker="o", alpha=0.2, ms=2, color=GREY),
)
colors_box = [BLUE, TEAL]
for patch, col in zip(bp["boxes"], colors_box):
    patch.set_facecolor(col); patch.set_alpha(0.6)
ax4m.axhline(0, color="black", lw=1, ls="--", alpha=0.5)
ax4m.set_ylabel("NPV ($M)")
ax4m.set_title("NPV Distribution\nBox Plot (10K sims)")

# Right: scatter — licensor vs licensee NPV
ax4r = axes4[2]
sample_idx = np.random.choice(N_SIMULATIONS, 2000, replace=False)
sc = ax4r.scatter(licensee_npvs[sample_idx], licensor_npvs[sample_idx],
                  alpha=0.15, s=6, c=licensor_npvs[sample_idx], cmap="RdYlBu")
ax4r.axvline(0, color="black", lw=0.8, ls="--")
ax4r.axhline(0, color="black", lw=0.8, ls="--")
corr = np.corrcoef(licensee_npvs, licensor_npvs)[0,1]
ax4r.text(0.05, 0.93, f"ρ = {corr:.2f}", transform=ax4r.transAxes, fontsize=9,
          color=BLUE, fontweight="bold")
ax4r.set_xlabel("Licensee eNPV ($M)")
ax4r.set_ylabel("Licensor Deal NPV ($M)")
ax4r.set_title("Licensee vs Licensor NPV\nCorrelation Scatter (2K sims)")
plt.colorbar(sc, ax=ax4r, label="Licensor NPV ($M)", shrink=0.8)

fig4.tight_layout()
fig4.savefig("/mnt/user-data/outputs/04_probability_analysis.png", dpi=150, bbox_inches="tight")
print("Saved: 04_probability_analysis.png")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — EXPORT SUMMARY TABLE TO CSV
# ══════════════════════════════════════════════════════════════════════════════

summary_rows = []
for i, y in enumerate(YEARS):
    summary_rows.append({
        "Year":               y,
        "Revenue_M":          round(base["revenue"][i], 3),
        "COGS_M":             round(base["revenue"][i]*COGS_PCT, 3),
        "Royalty_Paid_M":     round(base["royalty"][i], 3),
        "RD_Expense_M":       RD_SCHEDULE.get(i, 0.0),
        "FCF_Licensee_M":     round(base["fcf"][i], 3),
        "CumProb_Success":    round(base["cum_prob"][i], 4),
        "RiskAdj_FCF_M":      round(base["risk_adj_fcf"][i], 3),
        "DiscFactor_Licensee":round(base["df_licensee"][i], 4),
        "Disc_eNPV_M":        round(base["risk_adj_fcf"][i]*base["df_licensee"][i], 3),
        "Licensor_CF_M":      round(base["licensor_cf"][i], 3),
    })

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv("/mnt/user-data/outputs/05_base_case_table.csv", index=False)
print("Saved: 05_base_case_table.csv")

mc_df = pd.DataFrame({"Licensee_eNPV_M": licensee_npvs, "Licensor_NPV_M": licensor_npvs})
mc_df.to_csv("/mnt/user-data/outputs/06_monte_carlo_results.csv", index=False)
print("Saved: 06_monte_carlo_results.csv")


print("\n✅  All outputs saved.")
print(f"\n   Base case Licensee eNPV : ${base_enpv:.2f}M")
print(f"   Base case Licensor NPV  : ${run_scenario()['licensor_npv']:.2f}M")
print(f"   MC Mean Licensee eNPV   : ${ls_stats['mean']:.2f}M")
print(f"   MC Mean Licensor NPV    : ${lr_stats['mean']:.2f}M")
print(f"   P(Licensee eNPV > 0)    : {ls_stats['prob_pos']*100:.1f}%")
print(f"   P(Licensor NPV > 0)     : {lr_stats['prob_pos']*100:.1f}%")
