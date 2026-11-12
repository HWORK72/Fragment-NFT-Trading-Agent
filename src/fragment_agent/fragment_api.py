from decimal import Decimal
import logging
import re
from typing import Any
import aiohttp
from src.fragment_agent.logger import get_logger

logger: logging.Logger = get_logger("FragmentBuyProtocol")


class FragmentPurchaseClient:
    def __init__(
        self,
        base_url: str = "https://fragment.com",
        cookie_token: str = "",
        cookie_ssid: str = "",
        cookie_ton_token: str = "",
        cookie_dt: str = "-180",
        http_proxy: str | None = None,
    ) -> None:
        self._base_url: str = base_url
        self._cookie_token: str = cookie_token
        self._cookie_ssid: str = cookie_ssid
        self._cookie_ton_token: str = cookie_ton_token
        self._cookie_dt: str = cookie_dt
        self._proxy: str | None = http_proxy
        self._session: aiohttp.ClientSession | None = None
        self._api_hash: str = ""

    async def initialize(self) -> None:
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/gifts",
        }
        cookies: dict[str, str] = {"stel_dt": self._cookie_dt}
        if self._cookie_token:
            cookies["stel_token"] = self._cookie_token
        if self._cookie_ssid:
            cookies["stel_ssid"] = self._cookie_ssid
        if self._cookie_ton_token:
            cookies["stel_ton_token"] = self._cookie_ton_token

        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=15.0)
        self._session = aiohttp.ClientSession(
            base_url=self._base_url,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            trust_env=True,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def extract_api_hash_from_html(self, html: str) -> str:
        match: re.Match[str] | None = re.search(
            r'apiUrl["\']:\s*["\']\\?/api\?hash=([a-f0-9]+)["\']', html
        )
        if match:
            self._api_hash = match.group(1)
            logger.info("FRAGMENT API HASH EXTRACTED: %s", self._api_hash)
            return self._api_hash
        return ""

    async def get_buy_order_payload(
        self,
        item_id: str,
        collection_slug: str,
        price_ton: Decimal,
    ) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("Fragment purchase session not initialized")

        slug_formatted: str = item_id.replace("_", "-")

        if not self._api_hash:
            endpoint_check: str = f"/gift/{slug_formatted}"
            try:
                resp: aiohttp.ClientResponse
                async with self._session.get(endpoint_check, proxy=self._proxy) as resp:
                    if resp.status == 200:
                        text_data: str = await resp.text()
                        self.extract_api_hash_from_html(text_data)
            except Exception as err:
                logger.warning("Failed probing API hash: %s", str(err))

        if self._api_hash:
            request_path: str = f"/api?hash={self._api_hash}"
            methods_to_try: tuple[str, ...] = ("getBidLink", "initGiftBuy")
            method_name: str
            for method_name in methods_to_try:
                payload_body: dict[str, str] = {
                    "method": method_name,
                    "type": "gifts",
                    "id": slug_formatted,
                    "bid": str(price_ton),
                    "transaction": "1",
                }
                try:
                    response: aiohttp.ClientResponse
                    async with self._session.post(
                        request_path,
                        data=payload_body,
                        proxy=self._proxy,
                    ) as response:
                        if response.status != 200:
                            continue
                        data_json: dict[str, Any] = await response.json()
                        parsed_contract: dict[str, Any] | None = self._extract_tx_from_response(
                            data_json, price_ton
                        )
                        if parsed_contract is not None:
                            logger.info(
                                "LIVE FRAGMENT CONTRACT GENERATED FOR %s VIA %s",
                                slug_formatted,
                                method_name,
                            )
                            return parsed_contract
                except Exception as api_err:
                    logger.debug("Fragment API method %s notice: %s", method_name, str(api_err))

        return {
            "destination": "",
            "amount_ton": price_ton,
            "payload_boc": f"gift_buy_{slug_formatted}",
            "is_live_contract": False,
        }

    def _extract_tx_from_response(
        self,
        data_json: dict[str, Any],
        fallback_price: Decimal,
    ) -> dict[str, Any] | None:
        tx_obj: Any = data_json.get("transaction")
        if isinstance(tx_obj, dict):
            messages: Any = tx_obj.get("messages")
            if isinstance(messages, list) and len(messages) > 0:
                first_msg: dict[str, Any] = messages[0]
                address_str: str = str(first_msg.get("address", ""))
                raw_amount: str = str(first_msg.get("amount", "0"))
                payload_str: str = str(
                    first_msg.get("payload", first_msg.get("body", ""))
                )
                if address_str:
                    amount_ton: Decimal = (
                        (Decimal(raw_amount) / Decimal("1000000000"))
                        if raw_amount.isdigit() and int(raw_amount) > 1000000
                        else fallback_price
                    )
                    return {
                        "destination": address_str,
                        "amount_ton": amount_ton,
                        "payload_boc": payload_str,
                        "is_live_contract": True,
                    }

        res_obj: Any = data_json.get("result")
        if isinstance(res_obj, dict):
            addr: str = str(res_obj.get("address", ""))
            if addr:
                return {
                    "destination": addr,
                    "amount_ton": Decimal(str(res_obj.get("amount", str(fallback_price)))),
                    "payload_boc": str(res_obj.get("payload", "")),
                    "is_live_contract": True,
                }

        return None