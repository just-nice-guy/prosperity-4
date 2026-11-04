from __future__ import annotations

from pydantic import BaseModel, Field


class RoundDaySelection(BaseModel):
    round_num: int = Field(..., ge=0)
    day_num: int


class RunCreateRequest(BaseModel):
    trader_path: str
    round_days: list[RoundDaySelection]
    matching_mode: str = "prosperity"
    fill_probability: float = 0.005
    activity_boost: float = 0.003
    random_seed: int | None = None
    sigma: float = 0.0
    edge_fill_boost: float = 0.0
    limit_overrides: dict[str, int] = Field(default_factory=dict)
    data_roots: list[str] = Field(default_factory=list)
    time_limit_ms: int = 900


class MonteCarloCreateRequest(BaseModel):
    trader_path: str
    round_days: list[RoundDaySelection]
    num_paths: int = Field(50, ge=2, le=500)
    base_seed: int | None = None
    fill_probability: float = 0.005
    activity_boost: float = 0.003
    sigma: float = 0.0
    edge_fill_boost: float = 0.0
    limit_overrides: dict[str, int] = Field(default_factory=dict)
    data_roots: list[str] = Field(default_factory=list)
    time_limit_ms: int = 900
    fill_skip_prob: float = Field(0.0, ge=0.0, le=1.0)
    adverse_selection: float = Field(0.0, ge=0.0, le=10.0)
    min_fill_fraction: float = Field(0.5, ge=0.01, le=1.0)
    max_fill_fraction: float = Field(1.0, ge=0.01, le=1.0)


class CpcvCreateRequest(BaseModel):
    trader_path: str
    round_days: list[RoundDaySelection]
    n_groups: int = Field(6, ge=2, le=20)
    k_test_groups: int = Field(2, ge=1, le=19)
    purge_groups: int = Field(0, ge=0, le=5)
    embargo_pct: float = Field(0.0, ge=0.0, le=0.5)
    matching_mode: str = "invisible"
    fill_probability: float = 0.005
    activity_boost: float = 0.003
    sigma: float = 0.0
    edge_fill_boost: float = 0.0
    random_seed: int | None = None
    limit_overrides: dict[str, int] = Field(default_factory=dict)
    data_roots: list[str] = Field(default_factory=list)
    time_limit_ms: int = 900


class OfficialLogImportRequest(BaseModel):
    run_id: str
    label: str = "official-log"
    text: str


class OptimizationParameter(BaseModel):
    name: str
    min_value: float
    max_value: float
    step: float
    type: str = "float"


class OptimizationCreateRequest(BaseModel):
    trader_path: str
    round_days: list[RoundDaySelection]
    parameters: list[OptimizationParameter]
    search_method: str = "grid"
    search_budget: int = Field(50, ge=1, le=500)
    objective: str = "mean_pnl"
    is_fraction: float = Field(0.7, ge=0.3, le=0.95)
    cpcv_n: int = Field(5, ge=2, le=10)
    cpcv_k: int = Field(1, ge=1, le=4)
    purge_groups: int = Field(1, ge=0, le=3)
    embargo_pct: float = Field(0.0, ge=0.0, le=0.2)
    matching_mode: str = "invisible"
    fill_probability: float = 0.005
    activity_boost: float = 0.003
    sigma: float = 0.0
    edge_fill_boost: float = 0.0
    random_seed: int | None = None
    limit_overrides: dict[str, int] = Field(default_factory=dict)
    data_roots: list[str] = Field(default_factory=list)
    time_limit_ms: int = 900
    min_trades: int = Field(5, ge=0)
