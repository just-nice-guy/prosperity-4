export type DatasetInfo = {
  round_num: number;
  day_num: number;
  prices_file: string;
  trades_file: string | null;
  observations_file: string | null;
};

export type RunManifest = {
  run_id: string;
  status: string;
  trader_path?: string;
  datasets?: Array<{ round_num: number; day_num: number }>;
  matching_mode?: string;
};

export type RunSummary = {
  run_id: string;
  status: string;
  total_ticks: number;
  total_orders: number;
  total_fills: number;
  final_pnl: number;
  final_positions: Record<string, number>;
  cash_by_product: Record<string, number>;
  mark_to_market_by_product: Record<string, number>;
  dataset_summaries: Array<Record<string, unknown>>;
  config: Record<string, unknown>;
};

export type RunRecord = {
  run_id: string;
  manifest: RunManifest;
  summary: RunSummary | null;
  config: Record<string, unknown> | null;
};

export type ActivityRow = {
  round_num: string;
  day_num: string;
  timestamp: string;
  product: string;
  bid_price_1: string;
  bid_price_2: string;
  bid_price_3: string;
  bid_volume_1: string;
  bid_volume_2: string;
  bid_volume_3: string;
  ask_price_1: string;
  ask_price_2: string;
  ask_price_3: string;
  ask_volume_1: string;
  ask_volume_2: string;
  ask_volume_3: string;
  mid_price: string;
  position: string;
  cash: string;
  pnl: string;
};

export type OrderbookSnapshot = {
  round_num: number;
  day_num: number;
  timestamp: number;
  product: string;
  bid_prices: number[];
  bid_volumes: number[];
  ask_prices: number[];
  ask_volumes: number[];
  mid_price: number;
};

export type TradeRow = {
  round_num: number;
  day_num: number;
  timestamp: number;
  symbol: string;
  currency: string;
  price: number;
  quantity: number;
  buyer: string;
  seller: string;
  source: string;
};

export type RunLogs = {
  sandbox: string;
  decision_trace: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
};

export type RawPriceRow = {
  round_num: number;
  day_num: number;
  timestamp: number;
  best_bid: number | null;
  best_ask: number | null;
  mid_price: number;
};

export type RawTradeRow = {
  round_num: number;
  day_num: number;
  timestamp: number;
  price: number;
  quantity: number;
};

export type MonteCarloRun = {
  mc_id: string;
  status: string;
  num_paths: number;
  completed_paths: number;
  failed_paths: number;
  base_seed: number | null;
  child_run_ids: string[];
  children: Array<{ run_id: string; status: string; final_pnl: number | null }>;
  trader_path: string;
  matching_mode: string;
  created_at: string;
};

export type MonteCarloResults = {
  mc_id: string;
  status: string;
  num_paths: number;
  completed_paths: number;
  pnl_paths: Record<string, Array<[number, number]>>;
  final_pnl_distribution: number[];
  risk_metrics: {
    mean_pnl: number | null;
    median_pnl: number | null;
    std_dev: number | null;
    percentile_5: number | null;
    percentile_25: number | null;
    percentile_75: number | null;
    percentile_95: number | null;
    probability_of_loss: number | null;
    max_drawdown_mean: number | null;
    max_drawdown_worst: number | null;
    sharpe_estimate: number | null;
    var_95: number | null;
    cvar_95: number | null;
  };
};

export type CpcvRun = {
  cpcv_id: string;
  status: string;
  n_groups: number;
  k_test_groups: number;
  purge_groups: number;
  embargo_pct: number;
  total_combinations: number;
  completed_combinations: number;
  failed_combinations: number;
  children: Array<{
    run_id: string;
    combination: number[];
    status: string;
    final_pnl: number | null;
  }>;
  total_ticks: number | null;
  groups_tick_counts: number[];
  trader_path: string;
  matching_mode: string;
  created_at: string;
};

export type CpcvResults = {
  cpcv_id: string;
  status: string;
  total_combinations: number;
  completed_combinations: number;
  n_groups: number;
  k_test_groups: number;
  path_results: Array<{
    run_id: string;
    combination: number[];
    final_pnl: number;
    pnl_per_fold: Record<string, number>;
  }>;
  metrics: {
    n_paths: number;
    mean_pnl: number | null;
    median_pnl: number | null;
    std_pnl: number | null;
    pbo: number | null;
    psr: number | null;
    dsr: number | null;
    sharpe_hat: number | null;
    e_max_sharpe: number | null;
    skewness: number | null;
    excess_kurtosis: number | null;
    percentile_5: number | null;
    percentile_25: number | null;
    percentile_75: number | null;
    percentile_95: number | null;
    fold_avg_pnl: Record<string, number>;
    fold_std_pnl: Record<string, number>;
  };
};

export type DiscoveredParam = {
  name: string;
  default_value: number;
  type: "int" | "float";
  line: number;
};

export type OptimizationRun = {
  opt_id: string;
  status: string;
  trader_path: string;
  parameters: Array<{ name: string; min_value: number; max_value: number; step: number }>;
  search_method: string;
  objective: string;
  is_fraction: number;
  cpcv_n: number;
  cpcv_k: number;
  total_combinations: number;
  cpcv_paths_per_combo: number;
  total_runs: number;
  completed_runs: number;
  total_ticks: number;
  is_ticks: number;
  oos_ticks: number;
  matching_mode: string;
  created_at: string;
};

export type OptCombinationResult = {
  combo_idx: number;
  rank: number;
  overrides: Record<string, number>;
  is_n_paths: number;
  is_total_fills: number;
  completed: boolean;
  is_mean_pnl: number | null;
  is_median_pnl: number | null;
  is_std_pnl: number | null;
  is_min_pnl: number | null;
  is_max_pnl: number | null;
  is_sharpe: number | null;
  is_pbo: number | null;
  is_win_rate: number | null;
  is_dsharpe: number | null;
  is_pnls: number[];
  oos_pnl: number | null;
  is_oos_ratio: number | null;
};

export type OptimizationResults = {
  opt_id: string;
  status: string;
  objective: string;
  combination_results: OptCombinationResult[];
  best_combo_idx: number | null;
  deflated_sharpe: number | null;
  n_trials: number;
};

export type RuntimeSettings = {
  max_concurrent_runs: number;
  cleanup_temp_traders: boolean;
  max_optimization_combos: number;
  max_total_runs: number;
  cpu_limit: number;
  ram_limit_mb: number;
};

export type SystemInfo = {
  cpu_logical: number;
  cpu_physical: number;
  cpu_percent: number;
  ram_total_mb: number;
  ram_available_mb: number;
  ram_used_mb: number;
  ram_percent: number;
  worker_count: number;
  worker_pids: number[];
  worker_ram_mb: number;
};

export type ComparisonRecord = {
  comparison_id: string;
  run_id: string;
  label: string;
  local: Record<string, unknown>;
  official: Record<string, unknown>;
  diff: Record<string, unknown>;
  official_log: {
    sandbox_lines: string[];
    activity_rows: Array<Record<string, string>>;
    trade_rows: Array<Record<string, string>>;
  };
};
