import asyncio
from decimal import Decimal
import logging
import socket
from typing import Any
import aiohttp

logger: logging.Logger = logging.getLogger("TelegramAlerts")


class TelegramAlertService:
    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
    ) -> None:
        self._bot_token: str = bot_token
        self._chat_id: str = chat_id
        self._session: aiohttp.ClientSession | None = None
        self._is_enabled: bool = bool(bot_token and chat_id)

    async def initialize(self) -> None:
        if self._is_enabled:
            connector: aiohttp.TCPConnector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                ssl=True,
            )
            timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=15.0)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                trust_env=True,
            )
            logger.info("Telegram Alert Dispatcher active (trust_env=True). Chat ID: %s", self._chat_id)
        else:
            logger.info("Telegram Alerts disabled (token or chat_id not set in .env).")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _send_html_message(self, text_html: str) -> bool:
        if not self._is_enabled or self._session is None:
            return False

        api_url: str = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp: aiohttp.ClientResponse
            async with self._session.post(api_url, json=payload) as resp:
                if resp.status == 200:
                    return True
                error_body: str = await resp.text()
                logger.warning("Telegram API rejected message with status %d: %s", resp.status, error_body)
                return False
        except Exception as alert_err:
            logger.error("Failed sending Telegram alert: %s (%s)", type(alert_err).__name__, repr(alert_err))
            return False

    async def send_startup_ping(self, wallet_address: str, balance_ton: Decimal) -> None:
        msg: str = (
            "<b>FRAGMENT AGENT OPERATIONAL</b>\n\n"
            f"<b>Wallet:</b> <code>{wallet_address}</code>\n"
            f"<b>On-Chain Balance:</b> {balance_ton} TON\n"
            "<b>Status:</b> Live Market Monitoring Active."
        )
        await self._send_html_message(msg)

    async def send_opportunity_alert(
        self,
        auction_id: str,
        model: str,
        backdrop: str,
        price_ton: Decimal,
        floor_ton: Decimal,
        is_black: bool,
        item_url: str,
    ) -> None:
        discount_ton: Decimal = floor_ton - price_ton
        discount_pct: Decimal = (discount_ton / floor_ton) * Decimal("100")
        rarity_badge: str = "BLACK BACKDROP RARE" if is_black else "COMMON ASSET"

        msg: str = (
            f"<b>OPPORTUNITY DETECTED ({rarity_badge})</b>\n\n"
            f"<b>Item:</b> {model.capitalize()}\n"
            f"<b>ID:</b> <code>{auction_id}</code>\n"
            f"<b>Backdrop:</b> {backdrop}\n"
            f"<b>Asking Price:</b> {price_ton} TON\n"
            f"<b>Market Floor:</b> {floor_ton} TON\n"
            f"<b>Projected Margin:</b> +{discount_ton.quantize(Decimal('0.01'))} TON ({discount_pct.quantize(Decimal('0.1'))}%)\n\n"
            f"<a href='{item_url}'>Open on Fragment</a>"
        )
        await self._send_html_message(msg)