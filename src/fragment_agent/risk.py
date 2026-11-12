from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from src.fragment_agent.config import AgentSettings
from src.fragment_agent.logger import get_logger
from src.fragment_agent.models import GiftAuction

logger: logging.Logger = get_logger("FragmentRisk")


class RiskManager:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings: AgentSettings = settings
        self._wallet_balance: Decimal = settings.ton_wallet_balance
        self._spend_records: list[tuple[datetime, Decimal]] = []
        self._active_positions_count: int = 0
        self._consecutive_errors: int = 0
        self._circuit_broken_until: datetime | None = None

    def set_wallet_balance(self, live_balance: Decimal) -> None:
        spent_24h: Decimal = self.get_24h_spent()
        adjusted_balance: Decimal = max(Decimal("0.0"), live_balance - spent_24h)
        self._wallet_balance = adjusted_balance

    def get_wallet_balance(self) -> Decimal:
        return self._wallet_balance

    def get_24h_spent(self) -> Decimal:
        cutoff: datetime = datetime.now(timezone.utc) - timedelta(hours=24)
        self._spend_records = [
            record for record in self._spend_records if record[0] >= cutoff
        ]
        return sum(
            (amount for _, amount in self._spend_records),
            Decimal("0.0"),
        )

    def commit_allocation(self, amount: Decimal) -> None:
        self._spend_records.append((datetime.now(timezone.utc), amount))
        self._wallet_balance = max(Decimal("0.0"), self._wallet_balance - amount)
        self._active_positions_count += 1
        logger.info(
            "CAPITAL ALLOCATED: %s TON | Remaining Spendable Balance: %s TON | Active Positions: %d/%d",
            amount,
            self._wallet_balance,
            self._active_positions_count,
            self._settings.max_concurrent_auctions,
        )

    def record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self._settings.max_consecutive_errors:
            self._circuit_broken_until = datetime.now(timezone.utc) + timedelta(
                seconds=self._settings.circuit_breaker_cooloff_sec
            )
            logger.error(
                "Circuit breaker activated. Cooling down until %s",
                self._circuit_broken_until.isoformat(),
            )

    def record_success(self) -> None:
        self._consecutive_errors = 0

    def is_circuit_broken(self) -> bool:
        if self._circuit_broken_until is None:
            return False
        if datetime.now(timezone.utc) >= self._circuit_broken_until:
            self._circuit_broken_until = None
            self._consecutive_errors = 0
            logger.info("Circuit breaker cooloff finished. Operations resumed.")
            return False
        return True

    def validate_trade_opportunity(
        self,
        item: GiftAuction,
        fair_value: Decimal,
    ) -> tuple[bool, str]:
        if self.is_circuit_broken():
            return False, "Circuit breaker active"

        if self._active_positions_count >= self._settings.max_concurrent_auctions:
            return (
                False,
                f"Max concurrent positions limit reached ({self._settings.max_concurrent_auctions})",
            )

        if self._wallet_balance <= Decimal("0.0"):
            return False, "Zero on-chain balance: awaiting funds"

        if item.current_bid > self._settings.max_bid_per_item_ton:
            return (
                False,
                f"Price {item.current_bid} TON exceeds limit {self._settings.max_bid_per_item_ton} TON",
            )

        spent_24h: Decimal = self.get_24h_spent()
        if (spent_24h + item.current_bid) > self._settings.daily_budget_ton:
            return (
                False,
                f"Daily budget limit exceeded: {spent_24h + item.current_bid} TON > {self._settings.daily_budget_ton} TON",
            )

        if (self._wallet_balance - item.current_bid) < self._settings.min_balance_reserve_ton:
            return (
                False,
                f"Balance reserve breach: balance {self._wallet_balance} TON cannot cover {item.current_bid} TON + reserve {self._settings.min_balance_reserve_ton} TON",
            )

        discount_threshold: Decimal = fair_value * (
            Decimal("1") - (self._settings.target_discount_pct / Decimal("100"))
        )
        if item.current_bid > discount_threshold:
            return (
                False,
                f"Price {item.current_bid} TON exceeds threshold {discount_threshold.quantize(Decimal('0.01'))} TON",
            )

        return True, "Valid trade opportunity approved"