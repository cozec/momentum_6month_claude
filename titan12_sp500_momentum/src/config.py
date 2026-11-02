"""Configuration defaults for the Titan-12 Momentum Rotation backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class BacktestConfig:
    """Runtime configuration for a Titan-12 backtest."""

    start_date: str = "2016-01-01"
    end_date: str = "2026-05-12"
    universe: str = "sp500"
    benchmark: str = "SPY"
    top_n: int = 3
    lookback_months: int = 12
    weights: list[int] = field(
        default_factory=lambda: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    )
    rebalance_frequency: str = "monthly"
    initial_capital: float = 100000.0
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 5.0
    use_historical_membership: bool = True
    min_price_history_months: int = 12
    refresh_data: bool = False
    include_gspc: bool = False
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    raw_price_dir: Path = PROJECT_ROOT / "data" / "raw_prices"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    membership_path: Path = PROJECT_ROOT / "data" / "sp500_membership.csv"
    output_dir: Path = PROJECT_ROOT / "outputs"
    chart_dir: Path = PROJECT_ROOT / "outputs" / "charts"
    log_dir: Path = PROJECT_ROOT / "logs"
    data_quality_path: Path = PROJECT_ROOT / "logs" / "data_quality_report.csv"
    backtest_log_path: Path = PROJECT_ROOT / "logs" / "backtest.log"
    summary_path: Path = PROJECT_ROOT / "summary.md"

    @property
    def membership_mode(self) -> str:
        """Return the active membership mode name."""

        if self.use_historical_membership:
            return "historical_constituents"
        return "current_constituents"


def ensure_directories(config: BacktestConfig) -> None:
    """Create project output and cache directories required by the backtest."""

    for path in (
        config.data_dir,
        config.raw_price_dir,
        config.processed_dir,
        config.output_dir,
        config.chart_dir,
        config.log_dir,
        config.project_root / "plots",
        config.project_root / "results",
    ):
        path.mkdir(parents=True, exist_ok=True)
