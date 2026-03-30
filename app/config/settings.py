from __future__ import annotations

from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunMode(str, Enum):
    STOPPED = "stopped"
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "safe-arbitrage-bot"
    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "sqlite:///./arbitrage.db"
    sql_echo: bool = False
    auto_create_schema: bool = False

    timezone: str = "UTC"

    mode: RunMode = RunMode.PAPER
    live_enable_flag: bool = False
    live_execution_enabled: bool = False
    live_confirmation_token: SecretStr = SecretStr("DISABLED")
    control_api_token: SecretStr = SecretStr("change-me")
    allow_live_without_token: bool = False

    global_kill_switch: bool = False

    # RPC and chain safety
    hyperevm_chain_id: int = 999
    hyperevm_rpc_url: str = "https://rpc.hyperliquid.xyz/evm"
    base_chain_id: int = 8453
    base_rpc_url: str = "https://mainnet.base.org"
    cex_request_timeout_seconds: float = 3.0
    cex_request_retries: int = 2

    # Asset addresses (placeholder; should be replaced in env)
    hyperevm_usdc: str = "0x0000000000000000000000000000000000000001"
    hyperevm_usdt0: str = "0x0000000000000000000000000000000000000002"
    hyperevm_usdc_decimals: int = 6
    hyperevm_usdt0_decimals: int = 6

    # HyperEVM DEX real-quoter configuration (empty => unsupported-safe)
    hyperevm_ramses_quoter: str = ""
    hyperevm_hybra_quoter: str = ""
    hyperevm_ramses_quoter_mode: str = "v2"
    hyperevm_hybra_quoter_mode: str = "v2"
    hyperevm_ramses_pool_usdc_usdt0: str = ""
    hyperevm_hybra_pool_usdc_usdt0: str = ""
    hyperevm_ramses_quoter_fee_tier: int = 5
    hyperevm_ramses_pool_fee_tier: int = 5
    hyperevm_ramses_economic_fee_bps: int = 5
    hyperevm_hybra_quoter_fee_tier: int = 5
    hyperevm_hybra_pool_fee_tier: int = 5
    hyperevm_hybra_economic_fee_bps: int = 5

    # Base DEX real-quoter configuration (empty => unsupported-safe)
    base_usdc_address: str = "0x0000000000000000000000000000000000000003"
    base_virtual_address: str = "0x0000000000000000000000000000000000000004"
    base_usdc_decimals: int = 6
    base_virtual_decimals: int = 18
    base_uniswap_quoter: str = ""
    base_uniswap_quoter_mode: str = "v2"
    base_uniswap_v3_pool: str = ""
    base_uniswap_quoter_fee_tier: int = 100
    base_uniswap_pool_fee_tier: int = 100
    base_uniswap_economic_fee_bps: int = 100
    base_pancake_quoter: str = ""
    base_pancake_quoter_mode: str = "v2"
    base_pancake_v3_pool: str = ""
    base_pancake_quoter_fee_tier: int = 100
    base_pancake_pool_fee_tier: int = 100
    base_pancake_economic_fee_bps: int = 100
    base_aerodrome_quoter: str = ""
    base_aerodrome_quoter_mode: str = "v2"
    base_aerodrome_pool: str = ""
    base_aerodrome_quoter_fee_tier: int = 100
    base_aerodrome_pool_fee_tier: int = 100
    base_aerodrome_economic_fee_bps: int = 100

    # Allowlists are comma-separated env values
    allowlisted_tokens: str = (
        "0x0000000000000000000000000000000000000001,"
        "0x0000000000000000000000000000000000000002"
    )
    allowlisted_routers: str = "0x0000000000000000000000000000000000000010"
    allowlisted_pools: str = (
        "ramses_v3_usdc_usdt0_5,hybra_v3_usdt0_usdc_5,"
        "ramses_v3_usdt0_usdc_5,hybra_v3_usdc_usdt0_5"
    )

    # HyperEVM live thresholds (conservative defaults)
    live_min_net_edge_bps: int = 30
    live_min_edge_persist_seconds: int = 8
    live_max_slippage_bps: int = 2
    live_min_profit_absolute_usdc: Decimal = Decimal("0.50")
    live_max_notional_usdc: Decimal = Decimal("100")
    live_max_notional_pct_of_smaller_pool: Decimal = Decimal("0.0002")
    live_max_trades_per_route_per_10m: int = 3
    live_max_consecutive_failures_per_route: int = 1
    live_max_consecutive_losses_per_route: int = 2
    route_failure_cooldown_seconds: int = 300
    route_fatal_failure_cooldown_seconds: int = 900
    global_daily_dd_stop_pct: Decimal = Decimal("0.005")
    global_stale_quote_stop_seconds: int = 3
    market_data_staleness_stop_seconds: int = 10
    health_snapshot_stale_seconds: int = 30

    # Depeg / abnormal defaults
    depeg_threshold_bps: int = 50
    rpc_error_rate_stop_pct_5m: Decimal = Decimal("0.05")
    gas_spike_multiplier: Decimal = Decimal("1.5")
    liquidity_drop_stop_pct: Decimal = Decimal("0.30")

    # Shadow defaults
    shadow_min_net_edge_bps: int = 125
    shadow_min_edge_persist_seconds: int = 20
    shadow_max_slippage_bps: int = 10
    shadow_notional_usdc: Decimal = Decimal("100")
    shadow_stale_quote_seconds: int = 5

    # Fee fallback (bps)
    bybit_maker_fee_bps_fallback: int = 10
    bybit_taker_fee_bps_fallback: int = 15
    mexc_maker_fee_bps_fallback: int = 0
    mexc_taker_fee_bps_fallback: int = 5
    cost_quote_drift_buffer_bps: int = 3
    cost_slippage_buffer_bps: int = 2
    cost_router_overhead_bps: int = 1
    cost_failed_tx_allowance_bps: int = 2
    cost_safety_margin_bps: int = 2

    # Alerts
    discord_webhook_url: str = ""
    alert_failure_stop_threshold: int = 10

    # Jobs
    quote_poll_interval_seconds: float = 1.0
    health_poll_interval_seconds: float = 5.0
    use_mock_market_data: bool = True
    mock_hyperevm_usdc_usdt0_mid: Decimal = Decimal("1.0000")
    mock_base_virtual_usdc_mid: Decimal = Decimal("1.0000")
    gas_price_gwei_default: Decimal = Decimal("0.05")
    gas_token_price_usdc: Decimal = Decimal("2500")

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: str | RunMode) -> RunMode:
        if isinstance(value, RunMode):
            return value
        normalized = str(value).strip().lower()
        if normalized not in {"stopped", "paper", "live"}:
            return RunMode.PAPER
        return RunMode(normalized)

    @property
    def allowlisted_tokens_set(self) -> set[str]:
        return {self._normalize_address(x) for x in self.allowlisted_tokens.split(",") if x.strip()}

    @property
    def allowlisted_routers_set(self) -> set[str]:
        return {self._normalize_address(x) for x in self.allowlisted_routers.split(",") if x.strip()}

    @property
    def allowlisted_pools_set(self) -> set[str]:
        return {x.strip() for x in self.allowlisted_pools.split(",") if x.strip()}

    @staticmethod
    def _normalize_address(raw: str) -> str:
        return raw.strip().lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


DecimalPositive = Annotated[Decimal, Field(gt=0)]
