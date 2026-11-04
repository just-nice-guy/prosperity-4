# IMC Prosperity 4 — Algorithmic Trading & Market Making

Code, research, and submissions from my participation in **IMC Prosperity 4** (April 2026), the algorithmic trading competition organized by **IMC**, as part of **JOJO Teams**.

The competition consists of 5 rounds across 2 phases. In each round, participants submit a Python `Trader` that trades simulated products against market bots, alongside a separate manual trading challenge.

This repository serves as my personal archive of the work, resources, and tools I developed or used throughout the competition.

It contains:
- **Trading algorithms:** strategy implementations and round submissions (market making, mean reversion, options, statistical signals).
- **Quantitative research:** exploratory analysis, model calibration, signal studies, and synthetic stress tests.
- **Local backtester:** a Python simulation engine with a FastAPI backend and React frontend for replaying and analyzing strategies.
- **Official submission logs:** execution logs and results downloaded from the competition platform.

## Team — JOJO Teams

I participated in IMC Prosperity 4 as part of **JOJO Teams**.

The work was divided **by asset, with each team member taking full responsibility for one assigned asset**. This included the entire process, from market data analysis and quantitative research to strategy design, implementation, calibration, backtesting, optimization, and final submission.

Each member independently managed their assigned asset, rather than splitting responsibilities by function.

**Note:** This is my personal repository, not a complete archive of the team's work. The `my_research/` directory contains exclusively my own research, experiments, and strategy development. Research conducted by other team members is not included.

The local backtesting engine is a fork of [Xeeshan85/imc-prosperity-4-backtester](https://github.com/Xeeshan85/imc-prosperity-4-backtester), subsequently modified and extended by **JOJO Teams**.

## Approach

- **Round 0 (tutorial):** `EMERALDS`, a stable product, and `TOMATOES`, a fluctuating one.
  First market-making baselines.

- **Round 1–2:** `ASH_COATED_OSMIUM` is mean-reverting around 10,000. `INTARIAN_PEPPER_ROOT`
  follows a near-deterministic linear trend.
  - Fair value from a multi-level, outlier-protected **micro-price**.
  - Rolling OLS for the trend and an **Ornstein–Uhlenbeck** model for mean reversion.
  - **Avellaneda–Stoikov** quoting with a target inventory. Fill-intensity parameters `A`, `k`
    are calibrated by maximum likelihood.
  - Strategies were stress-tested on synthetic regimes: trend reversals, flat markets, zig-zags.

- **Round 3–4:** options on `VELVETFRUIT_EXTRACT`.
  - Static no-arbitrage checks: strike monotonicity, vertical spreads, butterflies.
  - Empirical delta and gamma, surface residuals, market making with delta hedging.
  - Round 4 adds a study of which counterparties make or lose money, used as a signal.

- **Round 5:** 50 products. Per-product parameter search (trend / mean reversion, spread as a
  percentage of price), loaded into the trader from a parameter CSV.

## Repository Structure

```text
.
├── README.md
├── docs/
│   ├── doc.md                 # Prosperity 4 context: rules, data model, engine mechanics (FR)
│   ├── guide.md               # methodology / workflow playbook (FR)
│   └── media-kit.png
│
├── Stage0/Round0/Tomato/      # tutorial round: TOMATOES trader + platform logs
│
├── Stage1/                    # phase 1
│   ├── Round1/                # round 1 market data (prices/trades CSV)
│   │   ├── pepper/            # INTARIAN_PEPPER_ROOT: EDA, calibration, trader versions v1→v10,
│   │   │                      #   official backtest logs (backtestprosperity/)
│   │   ├── osmium/            # ASH_COATED_OSMIUM: analysis + official platform runs
│   │   ├── final/             # combined round 1 traders
│   │   ├── research/          # drift-flip signal studies
│   │   └── synthetic_datasets/# synthetic market scenarios + backtest results per trader version
│   └── Round2/                # round 2 market data, evaluation script, live logs of round 1
│
├── Stage2/                    # phase 2
│   ├── initial data/          # market data for rounds 3, 4 and 5 (read by the backtester)
│   ├── data clean/            # per-instrument option data + research outputs (CSV)
│   └── Round3/                # live logs of round 3
│
├── my_research/               # exclusively my personal research, round by round
│   ├── tutorial/ round1/ … round5/
│   │   ├── *.py               # strategy prototypes (OU, Avellaneda–Stoikov, micro-price, …)
│   │   ├── analyse/           # data loading / visualisation scripts
│   │   ├── submissions/       # submitted algorithms + official logs (<id>.py / .log / .json)
│   │   │   └── result/        # final submission of the round
│   │   └── idees.txt, analyse_produit.txt, … # research notes (FR)
│
├── claude research/           # PEPPER_ROOT microstructure report (figures + .docx) and the script that builds it
│
└── backtester/                # fork of Xeeshan85's backtester, modified by JOJO Teams
    ├── backend/               # matching engine, PnL, limits, Monte Carlo, CPCV, optimisation, tests
    ├── frontend/              # React/TypeScript UI: order book, PnL, positions, trades, log comparison
    └── docs/                  # simulation assumptions, UI principles, upstream audit
```

## Running the Code

**Requirements:** Python 3.12+ with `pandas`, `numpy`, and `matplotlib`. The backtester UI also requires Node.js.

**Backtester:**

```bash
# backend (API)
cd backtester/backend
python -m pip install -e .
python -m uvicorn prosperity4bt.api.app:app --reload

# frontend (web UI, http://127.0.0.1:5187)
cd backtester/frontend
npm install
npm run dev
```
