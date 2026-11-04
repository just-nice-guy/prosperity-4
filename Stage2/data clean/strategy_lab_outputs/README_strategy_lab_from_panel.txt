Strategy Lab Outputs - from advanced panel
=========================================

Input directory:
D:\dossier\Bureau\perplexity\round 3$\prosperity4\Stage2\data clean

This script assumes 12_advanced_option_panel_compact.csv already exists.
It adds the missing execution/strategy diagnostics:

31_transition_probability_by_signal.csv
- Probability of delta-hedged option move up/down by signal bucket.

32_realistic_fill_model_tests.csv
- Compares touch fill, actual-trade fill, and conservative fill.
- Uses hedge-cost-adjusted delta-hedged markouts.

33_confirmed_signal_strategy_tests.csv
- Tests concrete rules:
  cheap surface + bullish book -> bid
  expensive surface + bearish book -> ask
  alpha score, agreement score, disagreement cases.

34_surface_residual_half_life_tests.csv
- Tests whether surface residuals mean-revert and at which horizon.

35_cross_strike_lead_lag_tests.csv
- Finds which strikes lead/follow other strikes.

36_underlying_stress_regime_tests.csv
- Measures fill quality by underlying stress regime.

37_quote_level_optimization_tests.csv
- Tests quote level 0/1/2/3 from best bid/ask.

38_walk_forward_day_validation.csv
- Checks rule stability by day.

39_ranked_strategy_candidates.csv
- Aggregated ranking of strategy candidates.

Important:
Trust trade-fill and conservative-fill tests more than touch-fill tests.
Touch-fill is usually optimistic.
