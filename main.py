import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import os
import random
import re
import sys
from typing import Any, Final
import aiohttp
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from alerts import TelegramAlertService
from blockchain import TonBlockchainClient
from database import (
    bulk_record_market_ticks,
    bulk_record_trade_decisions,
    init_database,
)
from fragment_api import FragmentPurchaseClient
from signer import TonTransactionSigner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger: logging.Logger = logging.getLogger("FragmentCore")


class AgentSettings(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fragment_base_url: str = Field(default="https://fragment.com")
    fragment_cookie_stel_token: str = Field(default="")
    fragment_cookie_stel_ssid: str = Field(default="")
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


class GiftAuction(BaseModel):
    auction_id: str
    title: str
    model: str
    gift_num: int
    backdrop: str
    is_black_backdrop: bool
    current_bid: Decimal
    bid_step: Decimal
    ends_at: datetime
    highest_bidder_is_me: bool
    url: str
    is_active: bool
    is_live_data: bool


class MarketMetrics(BaseModel):
    model: str
    is_black_backdrop: bool
    floor_price: Decimal
    average_price: Decimal
    median_price: Decimal
    sample_size: int
    last_updated: datetime


class BackdropClassifier:
    BLACK_KEYWORDS: Final[tuple[str, ...]] = (
        "black",
        "onyx",
        "obsidian",
        "pitch",
        "charcoal",
        "night",
        "dark",
        "черн",
    )

    @classmethod
    def is_black(cls, backdrop_name: str) -> bool:
        name_clean: str = backdrop_name.strip().lower()
        keyword: str
        for keyword in cls.BLACK_KEYWORDS:
            if keyword in name_clean:
                return True
        return False


class MarketAnalyzer:
    def __init__(self) -> None:
        self._price_history: dict[tuple[str, bool], list[Decimal]] = {}
        self._metrics_cache: dict[tuple[str, bool], MarketMetrics] = {}

    def record_price(self, model: str, is_black: bool, price: Decimal) -> None:
        key: tuple[str, bool] = (model.lower(), is_black)
        if key not in self._price_history:
            self._price_history[key] = []
        self._price_history[key].append(price)
        if len(self._price_history[key]) > 300:
            self._price_history[key].pop(0)
        self._recalculate(model.lower(), is_black)

    def _recalculate(self, model: str, is_black: bool) -> None:
        key: tuple[str, bool] = (model, is_black)
        prices: list[Decimal] = sorted(self._price_history.get(key, []))
        if not prices:
            return

        sample_size: int = len(prices)
        floor_val: Decimal = prices[0]

        mid_idx: int = sample_size // 2
        median_val: Decimal = (
            (prices[mid_idx - 1] + prices[mid_idx]) / Decimal("2")
            if sample_size % 2 == 0
            else prices[mid_idx]
        )

        calc_prices: list[Decimal] = prices
        if sample_size >= 10:
            trim_count: int = int(sample_size * 0.1)
            calc_prices = prices[trim_count : sample_size - trim_count]

        avg_val: Decimal = sum(calc_prices) / Decimal(str(len(calc_prices)))

        self._metrics_cache[key] = MarketMetrics(
            model=model,
            is_black_backdrop=is_black,
            floor_price=floor_val.quantize(Decimal("0.01")),
            average_price=avg_val.quantize(Decimal("0.01")),
            median_price=median_val.quantize(Decimal("0.01")),
            sample_size=sample_size,
            last_updated=datetime.now(timezone.utc),
        )

    def get_metrics(self, model: str, is_black: bool) -> MarketMetrics | None:
        return self._metrics_cache.get((model.lower(), is_black))

    def get_fair_value(self, model: str, is_black: bool) -> Decimal | None:
        metrics: MarketMetrics | None = self.get_metrics(model, is_black)
        if metrics is None or metrics.sample_size < 1:
            return None
        return metrics.floor_price


class RiskManager:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings: AgentSettings = settings
        self._wallet_balance: Decimal = settings.ton_wallet_balance
        self._spend_records: list[tuple[datetime, Decimal]] = []
        self._consecutive_errors: int = 0
        self._circuit_broken_until: datetime | None = None

    def set_wallet_balance(self, live_balance: Decimal) -> None:
        self._wallet_balance = live_balance

    def get_wallet_balance(self) -> Decimal:
        return self._wallet_balance

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

        if self._wallet_balance <= Decimal("0.0"):
            return False, "Zero on-chain balance: awaiting testnet funds"

        if item.current_bid > self._settings.max_bid_per_item_ton:
            return False, f"Price {item.current_bid} TON exceeds limit {self._settings.max_bid_per_item_ton} TON"

        if (self._wallet_balance - item.current_bid) < self._settings.min_balance_reserve_ton:
            return False, f"Balance reserve breach: balance {self._wallet_balance} TON cannot cover {item.current_bid} TON + reserve {self._settings.min_balance_reserve_ton} TON"

        discount_threshold: Decimal = fair_value * (
            Decimal("1") - (self._settings.target_discount_pct / Decimal("100"))
        )
        if item.current_bid > discount_threshold:
            return False, f"Price {item.current_bid} TON exceeds threshold {discount_threshold.quantize(Decimal('0.01'))} TON"

        return True, "Valid trade opportunity approved"


class FragmentClient:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings: AgentSettings = settings
        self._session: aiohttp.ClientSession | None = None
        self._request_lock: asyncio.Lock = asyncio.Lock()

    async def initialize(self) -> None:
        connector: aiohttp.TCPConnector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=4,
            ttl_dns_cache=300,
            ssl=True,
        )
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
            total=25.0,
            connect=10.0,
        )
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookies: dict[str, str] = {}
        if self._settings.fragment_cookie_stel_token:
            cookies["stel_token"] = self._settings.fragment_cookie_stel_token
        if self._settings.fragment_cookie_stel_ssid:
            cookies["stel_ssid"] = self._settings.fragment_cookie_stel_ssid

        self._session = aiohttp.ClientSession(
            base_url=self._settings.fragment_base_url,
            connector=connector,
            timeout=timeout,
            headers=headers,
            cookies=cookies,
            trust_env=True,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_live_market(self) -> list[GiftAuction]:
        if self._session is None:
            raise RuntimeError("HTTP session not initialized")

        gathered_items: list[GiftAuction] = []
        slug: str
        for slug in self._settings.tracked_models:
            endpoint_url: str = f"/gifts/{slug}?filter=sale&sort=price_asc"
            async with self._request_lock:
                try:
                    response: aiohttp.ClientResponse
                    async with self._session.get(
                        endpoint_url,
                        proxy=self._settings.http_proxy,
                    ) as response:
                        if response.status != 200:
                            continue
                        html_body: str = await response.text()
                        soup: BeautifulSoup = BeautifulSoup(html_body, "lxml")
                        parsed: list[GiftAuction] = self._parse_html(soup, slug)
                        gathered_items.extend(parsed)
                        logger.info(
                            "LIVE INGESTION: Collection [%s] -> %d active sale items parsed",
                            slug,
                            len(parsed),
                        )
                except Exception as net_err:
                    logger.warning("Failed fetching collection %s: %s", slug, str(net_err))
                    continue

        return gathered_items

    def _parse_html(self, soup: BeautifulSoup, collection_slug: str) -> list[GiftAuction]:
        results: list[GiftAuction] = []
        cards: list[Any] = soup.select(".tm-grid-item")

        card: Any
        for card in cards:
            try:
                status_block: Any = card.select_one(".tm-status-unavail")
                if status_block and "not for sale" in status_block.get_text(strip=True).lower():
                    continue

                price_elem: Any = card.select_one(".tm-grid-item-value, .tm-value, .icon-ton")
                if not price_elem:
                    continue

                price_raw: str = price_elem.get_text(strip=True).replace(",", "")
                price_match: re.Match[str] | None = re.search(r"(\d+(?:\.\d+)?)", price_raw)
                if not price_match:
                    continue

                price_val: Decimal = Decimal(price_match.group(1))

                href_attr: str = str(card.get("href", ""))
                match_id: re.Match[str] | None = re.search(r"[-_](\d+)", href_attr)
                item_num: int = int(match_id.group(1)) if match_id else random.randint(100, 99999)

                card_text: str = card.get_text(" ", strip=True)
                is_black: bool = BackdropClassifier.is_black(card_text)

                results.append(
                    GiftAuction(
                        auction_id=f"{collection_slug}_{item_num}",
                        title=f"{collection_slug.capitalize()} No. {item_num}",
                        model=collection_slug,
                        gift_num=item_num,
                        backdrop="Onyx Black" if is_black else "Standard",
                        is_black_backdrop=is_black,
                        current_bid=price_val,
                        bid_step=Decimal("1.0"),
                        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
                        highest_bidder_is_me=False,
                        url=f"{self._settings.fragment_base_url}{href_attr}",
                        is_active=True,
                        is_live_data=True,
                    )
                )
            except Exception as parse_err:
                logger.debug("Failed parsing card: %s", str(parse_err))
                continue

        return results


class LiveTradingSupervisor:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings: AgentSettings = settings
        self._analyzer: MarketAnalyzer = MarketAnalyzer()
        self._risk_manager: RiskManager = RiskManager(settings)
        self._client: FragmentClient = FragmentClient(settings)
        self._blockchain: TonBlockchainClient = TonBlockchainClient(use_testnet=settings.use_testnet)
        self._purchase_client: FragmentPurchaseClient = FragmentPurchaseClient(
            base_url=settings.fragment_base_url,
            cookie_token=settings.fragment_cookie_stel_token,
            cookie_ssid=settings.fragment_cookie_stel_ssid,
            http_proxy=settings.http_proxy,
        )
        self._signer: TonTransactionSigner | None = None
        self._alerts: TelegramAlertService = TelegramAlertService(
            bot_token=settings.telegram_alert_bot_token,
            chat_id=settings.telegram_alert_chat_id,
        )
        self._is_running: bool = False
        self._evaluated_orders: set[str] = set()

    async def start(self) -> None:
        self._is_running = True
        await init_database()
        await self._client.initialize()
        await self._blockchain.initialize()
        await self._purchase_client.initialize()
        await self._alerts.initialize()

        mnemonic_words: list[str] = self._settings.ton_wallet_mnemonic.strip().replace('"', '').split()
        if len(mnemonic_words) == 24:
            self._signer = TonTransactionSigner(
                mnemonic_words=mnemonic_words,
                use_testnet=self._settings.use_testnet,
            )
            await self._signer.initialize()
            logger.info("ON-CHAIN SIGNER INTEGRATED: Authorization layer operational.")

        net_label: str = "TESTNET" if self._settings.use_testnet else "MAINNET"
        logger.info("=== FULL COMMERCIAL PIPELINE ACTIVE [NETWORK: %s] ===", net_label)

        await self._sync_blockchain_balance()

        loop_counter: int = 0
        while self._is_running:
            try:
                loop_counter += 1
                if self._risk_manager.is_circuit_broken():
                    await asyncio.sleep(self._settings.poll_interval_seconds)
                    continue

                if loop_counter % 6 == 0:
                    await self._sync_blockchain_balance()

                live_items: list[GiftAuction] = await self._client.fetch_live_market()
                if not live_items:
                    await asyncio.sleep(self._settings.poll_interval_seconds)
                    continue

                self._risk_manager.record_success()

                ticks_batch: list[dict[str, Any]] = []
                item: GiftAuction
                for item in live_items:
                    self._analyzer.record_price(
                        item.model,
                        item.is_black_backdrop,
                        item.current_bid,
                    )
                    ticks_batch.append(
                        {
                            "collection": item.model,
                            "gift_num": item.gift_num,
                            "price_ton": item.current_bid,
                            "is_black_backdrop": item.is_black_backdrop,
                        }
                    )

                await bulk_record_market_ticks(ticks_batch)

                decisions_batch: list[dict[str, Any]] = []
                for item in live_items:
                    decision: dict[str, Any] | None = await self._evaluate_and_process_order(item)
                    if decision is not None:
                        decisions_batch.append(decision)

                if decisions_batch:
                    await bulk_record_trade_decisions(decisions_batch)

                if loop_counter % 2 == 0:
                    self._print_live_telemetry(live_items)

            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Live cycle anomaly: %s", str(err), exc_info=True)
                self._risk_manager.record_error()

            await asyncio.sleep(self._settings.poll_interval_seconds)

    async def _sync_blockchain_balance(self) -> None:
        account_info: dict[str, Any] = await self._blockchain.get_address_state(
            self._settings.ton_wallet_address
        )
        live_balance: Decimal = account_info.get("balance_ton", Decimal("0.0"))
        state_str: str = account_info.get("state", "uninitialized")
        self._risk_manager.set_wallet_balance(live_balance)

        logger.info(
            "ON-CHAIN SYNC: Address: %s | State: %s | Live Balance: %s TON",
            self._settings.ton_wallet_address,
            state_str,
            live_balance,
        )

    async def _evaluate_and_process_order(self, item: GiftAuction) -> dict[str, Any] | None:
        fair_val: Decimal | None = self._analyzer.get_fair_value(
            item.model, item.is_black_backdrop
        )
        if fair_val is None:
            return None

        state_key: str = f"{item.auction_id}_{item.current_bid}"
        if state_key in self._evaluated_orders:
            return None
        self._evaluated_orders.add(state_key)

        is_approved: bool
        reason: str
        is_approved, reason = self._risk_manager.validate_trade_opportunity(item, fair_val)

        verdict: str = "ENTER" if is_approved else "REJECT"

        if is_approved:
            logger.info(
                "[OPPORTUNITY DETECTED] ID:%s | Model: %s | Price: %s TON | Real Floor: %s TON | APPROVED BY RISK GUARD",
                item.auction_id,
                item.model,
                item.current_bid,
                fair_val,
            )

            order_payload: dict[str, Any] = await self._purchase_client.get_buy_order_payload(
                item_id=item.auction_id,
                collection_slug=item.model,
                price_ton=item.current_bid,
            )

            if self._signer is not None:
                await self._signer.execute_smart_contract_buy(
                    destination_contract=order_payload.get("destination", self._settings.ton_wallet_address),
                    amount_ton=order_payload.get("amount_ton", item.current_bid),
                    is_dry_run=self._settings.dry_run,
                    payload_data=order_payload.get("payload_boc"),
                )

            await self._alerts.send_opportunity_alert(
                auction_id=item.auction_id,
                model=item.model,
                backdrop=item.backdrop,
                price_ton=item.current_bid,
                floor_ton=fair_val,
                is_black=item.is_black_backdrop,
                item_url=item.url,
            )
        else:
            logger.info(
                "[LIVE PAPER TRADE -> REJECT] ID:%s [%s] Price: %s TON (Real Floor: %s TON) -> %s",
                item.auction_id,
                item.model,
                item.current_bid,
                fair_val,
                reason,
            )

        return {
            "auction_id": item.auction_id,
            "collection": item.model,
            "price_ton": item.current_bid,
            "floor_at_execution": fair_val,
            "verdict": verdict,
            "reason": reason,
        }

    def _print_live_telemetry(self, current_items: list[GiftAuction]) -> None:
        current_balance: Decimal = self._risk_manager.get_wallet_balance()
        net_str: str = "Testnet" if self._settings.use_testnet else "Mainnet"
        logger.info("=== LIVE MARKET & BLOCKCHAIN SNAPSHOT [%s] ===", net_str)
        logger.info("Real TON Balance: %s TON", current_balance)
        logger.info("Total Real Assets for Sale: %d", len(current_items))

        processed_models: set[str] = set()
        item: GiftAuction
        for item in current_items:
            if item.model not in processed_models:
                processed_models.add(item.model)
                metrics: MarketMetrics | None = self._analyzer.get_metrics(item.model, item.is_black_backdrop)
                floor_val: str = str(metrics.floor_price) if metrics else "N/A"
                avg_val: str = str(metrics.average_price) if metrics else "N/A"
                logger.info(
                    "Collection [%s] | For Sale: %d | Real Floor: %s TON | Real Avg: %s TON",
                    item.model,
                    metrics.sample_size if metrics else 0,
                    floor_val,
                    avg_val,
                )
        logger.info("=========================================")

    async def stop(self) -> None:
        self._is_running = False
        await self._client.close()
        await self._blockchain.close()
        await self._purchase_client.close()
        await self._alerts.close()
        if self._signer is not None:
            await self._signer.close()
        logger.info("Engine shutdown complete.")


async def main() -> None:
    settings: AgentSettings = AgentSettings()
    supervisor: LiveTradingSupervisor = LiveTradingSupervisor(settings)
    try:
        await supervisor.start()
    except asyncio.CancelledError:
        pass
    finally:
        await supervisor.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application execution stopped cleanly by user signal.")