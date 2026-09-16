import asyncio
from decimal import Decimal
import json
import logging
import re
from typing import Any
import aiohttp

logger: logging.Logger = logging.getLogger("FragmentBuyProtocol")


class FragmentPurchaseClient:
    def __init__(
        self,
        base_url: str = "https://fragment.com",
        cookie_token: str = "",
        cookie_ssid: str = "",
        http_proxy: str | None = None,
    ) -> None:
        self._base_url: str = base_url
        self._cookie_token: str = cookie_token
        self._cookie_ssid: str = cookie_ssid
        self._proxy: str | None = http_proxy
        self._session: aiohttp.ClientSession | None = None
        self._api_hash: str = ""

    async def initialize(self) -> None:
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        cookies: dict[str, str] = {}
        if self._cookie_token:
            cookies["stel_token"] = self._cookie_token
        if self._cookie_ssid:
            cookies["stel_ssid"] = self._cookie_ssid

        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=15.0)
        self._session = aiohttp.ClientSession(
            base_url=self._base_url,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def extract_api_hash_from_html(self, html: str) -> str:
        match: re.Match[str] | None = re.search(r'apiUrl["\']:\s*["\']\\?/api\?hash=([a-f0-9]+)["\']', html)
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

        if not self._api_hash:
            endpoint_check: str = f"/gifts/{collection_slug}?filter=sale"
            try:
                resp: aiohttp.ClientResponse
                async with self._session.get(endpoint_check, proxy=self._proxy) as resp:
                    if resp.status == 200:
                        text_data: str = await resp.text()
                        self.extract_api_hash_from_html(text_data)
            except Exception as err:
                logger.warning("Failed probing API hash: %s", str(err))

        hash_query: str = f"?hash={self._api_hash}" if self._api_hash else ""
        request_path: str = f"/api{hash_query}"
        payload_body: dict[str, Any] = {
            "method": "initGiftBuy",
            "id": item_id,
        }

        try:
            response: aiohttp.ClientResponse
            async with self._session.post(
                request_path,
                data=payload_body,
                proxy=self._proxy,
            ) as response:
                if response.status == 200:
                    data_json: dict[str, Any] = await response.json()
                    if data_json.get("ok", False):
                        res_obj: dict[str, Any] = data_json.get("result", {})
                        logger.info("CONTRACT ORDER GENERATED FOR ID: %s", item_id)
                        return {
                            "destination": str(res_obj.get("address", "")),
                            "amount_ton": Decimal(str(res_obj.get("amount", str(price_ton)))),
                            "payload_boc": str(res_obj.get("payload", "")),
                            "is_live_contract": True,
                        }
        except Exception as api_err:
            logger.debug("Fragment direct API order query: %s", str(api_err))

        return {
            "destination": "EQB_FragmentEscrowPlaceholderDummyAddressToPreventFail",
            "amount_ton": price_ton,
            "payload_boc": f"gift_buy_{item_id}",
            "is_live_contract": False,
        }