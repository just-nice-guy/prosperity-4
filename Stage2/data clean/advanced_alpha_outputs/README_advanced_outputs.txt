Advanced option alpha diagnostics.

Input directory:
D:\dossier\Bureau\perplexity\round 3$\prosperity4\Stage2\data clean

Read first:
1. 15_fill_toxicity_by_signal_bucket.csv
2. 16_composite_alpha_strategy_tests.csv
3. 18_best_signals_ranked.csv
4. 11_empirical_delta_by_horizon.csv

Important:
- Touch-fill is approximate: it checks whether the trade at horizon h touches the current quote.
- It does not model queue position, latency, cancellations or self-trading.
- Use these outputs to rank alpha candidates, not as final executable PnL.
