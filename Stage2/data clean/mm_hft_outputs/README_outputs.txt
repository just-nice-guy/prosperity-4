# Market Making / HFT Diagnostic Outputs

Input underlying:
velvetfruit_extract.csv

Option files:
vev_4000.csv
vev_4500.csv
vev_5000.csv
vev_5100.csv
vev_5200.csv
vev_5300.csv
vev_5400.csv
vev_5500.csv
vev_6000.csv
vev_6500.csv

Horizons in rows/ticks:
[1, 2, 5, 10, 25, 50, 100]

Files produced:

01_instrument_microstructure_summary.csv
- Spread, depth, quote-change rate, trade activity and short-term volatility per product.

02_option_underlying_panel_compact.csv
- Merged option + underlying panel with moneyness, intrinsic value, time value and future moves.

03_empirical_delta_gamma_by_strike.csv
- Empirical delta from regression dC ~ dS and crude convexity proxy from dC ~ dS + dS².

04_underlying_predictive_alpha_tests.csv
- Tests whether underlying order-book features predict future underlying moves.

05_option_panel_predictive_alpha_tests.csv
- Tests whether underlying/option/surface features predict future option or underlying moves.

06_passive_mm_markout_summary.csv
- Passive buy/sell markouts by strike and horizon, raw and delta-hedged.
- Positive mean means the passive quote was profitable under the simplified fill assumption.

07_passive_mm_markouts_by_signal_bucket.csv
- Conditional markouts by buckets of imbalance, microprice edge, moneyness, time value and spread.
- This is the most useful file to find when to quote aggressively or avoid quoting.

08_surface_snapshot_diagnostics.csv
- Number of monotonicity/convexity violations across call strikes at each timestamp.

09_surface_violations.csv
- Detailed call-surface violation events.

10_optional_bs_iv_sample_assumed_T.csv
- Only produced if --compute_iv 1.
- IV is approximate because the true expiry/time-to-expiry is not in the CSV.
