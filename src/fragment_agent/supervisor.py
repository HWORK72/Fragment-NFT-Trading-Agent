import asyncio
from decimal import Decimal
import logging
from pathlib import Path
import subprocess
from typing import Any
from src.fragment_agent.alerts import TelegramAlertService
from src.fragment_agent.analyzer import MarketAnalyzer
from src.fragment_agent.blockchain import TonBlockchainClient
from src.fragment_agent.config import AgentSettings
from src.fragment_agent.database import (
    bulk_record_market_ticks,
    bulk_record_trade_decisions,
    init_database,
)
from src.fragment_agent.fragment_api import FragmentPurchaseClient
from src.fragment_agent.logger import BASE_DIR, get_logger
from src.fragment_agent.models import GiftAuction, MarketMetrics
from src.fragment_agent.risk import RiskManager
from src.fragment_agent.scraper import FragmentClient
from src.fragment_agent.signer import TonTransactionSigner

logger: logging.Logger = get_logger("FragmentSupervisor")
csharp_logger: logging.Logger = get_logger("FragmentQuantCSharp")


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
            cookie_ton_token=settings.fragment_cookie_stel_ton_token,
            cookie_dt=settings.fragment_cookie_stel_dt,
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

        mnemonic_words: list[str] = (
            self._settings.ton_wallet_mnemonic.strip().replace('"', "").split()
        )
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

                if loop_counter == 1 or loop_counter % 2 == 0:
                    self._print_live_telemetry(live_items)
                    await asyncio.to_thread(self._invoke_csharp_quant_engine)

            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Live cycle anomaly: %s", str(err), exc_info=True)
                self._risk_manager.record_error()

            await asyncio.sleep(self._settings.poll_interval_seconds)

    def _invoke_csharp_quant_engine(self) -> None:
        exe_candidates: list[Path] = [
            BASE_DIR / "src" / "FragmentQuant.Engine" / "bin" / "Release" / "net8.0" / "FragmentQuant.Engine.exe",
            BASE_DIR / "src" / "FragmentQuant.Engine" / "bin" / "Debug" / "net8.0" / "FragmentQuant.Engine.exe",
        ]
        selected_exe: Path | None = None
        candidate: Path
        for candidate in exe_candidates:
            if candidate.exists():
                selected_exe = candidate
                break

        if selected_exe is None:
            return

        try:
            completed: subprocess.CompletedProcess[str] = subprocess.run(
                [str(selected_exe), "--subordinate"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if completed.stdout:
                line: str
                for line in completed.stdout.splitlines():
                    clean_line: str = line.strip()
                    if clean_line:
                        csharp_logger.info(clean_line)
        except Exception as err:
            logger.warning("C# Quantitative Engine invocation notice: %s", str(err))

    async def _sync_blockchain_balance(self) -> None:
        account_info: dict[str, Any] = await self._blockchain.get_address_state(
            self._settings.ton_wallet_address
        )
        live_balance: Decimal = account_info.get("balance_ton", Decimal("0.0"))
        state_str: str = account_info.get("state", "uninitialized")

        effective_balance: Decimal = (
            max(live_balance, self._settings.ton_wallet_balance)
            if self._settings.dry_run
            else live_balance
        )
        self._risk_manager.set_wallet_balance(effective_balance)

        logger.info(
            "ON-CHAIN SYNC: Address: %s | State: %s | Live On-Chain: %s TON | Effective Balance: %s TON",
            self._settings.ton_wallet_address,
            state_str,
            live_balance,
            effective_balance,
        )

    async def _evaluate_and_process_order(self, item: GiftAuction) -> dict[str, Any] | None:
        fair_val: Decimal | None = self._analyzer.get_fair_value(
            item.model,
            item.is_black_backdrop,
            candidate_price=item.current_bid,
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
            self._risk_manager.commit_allocation(item.current_bid)
            logger.info(
                "[OPPORTUNITY DETECTED] ID:%s | Model: %s | Price: %s TON | Reference Floor: %s TON | APPROVED BY RISK GUARD",
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

            is_live_contract: bool = bool(order_payload.get("is_live_contract", False))
            destination_addr: str = str(order_payload.get("destination", ""))

            if not self._settings.dry_run and not is_live_contract:
                logger.warning(
                    "LIVE BUY SKIPPED FOR %s: Fragment did not return a live contract. Verify FRAGMENT_COOKIE_STEL_TON_TOKEN in .env",
                    item.auction_id,
                )
            elif self._signer is not None:
                target_dest: str = (
                    destination_addr if destination_addr else self._settings.ton_wallet_address
                )
                await self._signer.execute_smart_contract_buy(
                    destination_contract=target_dest,
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
                "[LIVE PAPER TRADE -> REJECT] ID:%s [%s] Price: %s TON (Ref Floor: %s TON) -> %s",
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
                metrics: MarketMetrics | None = self._analyzer.get_metrics(
                    item.model, item.is_black_backdrop
                )
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
