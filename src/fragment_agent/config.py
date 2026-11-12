from decimal import Decimal
from pathlib import Path
from typing import Final
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.fragment_agent.logger import BASE_DIR

ENV_FILE_PATH: Final[Path] = BASE_DIR / ".env"


class AgentSettings(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fragment_base_url: str = Field(default="https://fragment.com")
    fragment_cookie_stel_token: str = Field(default="")
    fragment_cookie_stel_ssid: str = Field(default="")
    fragment_cookie_stel_ton_token: str = Field(default="")
    fragment_cookie_stel_dt: str = Field(default="-180")
    ton_wallet_address: str = Field(default="0QDwnisxeXetFMi28eQX6I_ZLAvvAisjLyWl-_PmGoAHrOFA")
    ton_wallet_mnemonic: str = Field(default="")
    ton_wallet_balance: Decimal = Field(default=Decimal("2.0"))
    min_balance_reserve_ton: Decimal = Field(default=Decimal("0.2"))
    max_bid_per_item_ton: Decimal = Field(default=Decimal("10.0"))
    daily_budget_ton: Decimal = Field(default=Decimal("10.0"))
    max_concurrent_auctions: int = Field(default=3)
    target_discount_pct: Decimal = Field(default=Decimal("15.0"))
    max_valuation_markup_pct: Decimal = Field(default=Decimal("15.0"))
    poll_interval_seconds: float = Field(default=5.0)
    black_backdrop_only: bool = Field(default=False)
    dry_run: bool = Field(default=True)
    use_testnet: bool = Field(default=True)
    telegram_alert_bot_token: str = Field(default="")
    telegram_alert_chat_id: str = Field(default="")
    tracked_models: list[str] = Field(
        default_factory=lambda: [
            "homemadecake",
            "jollychimp",
            "astralshard",
        ]
    )
    http_proxy: str | None = Field(default=None)
    max_consecutive_errors: int = Field(default=3)
    circuit_breaker_cooloff_sec: int = Field(default=15)
