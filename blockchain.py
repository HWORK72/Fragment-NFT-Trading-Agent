import asyncio
from decimal import Decimal
import logging
from typing import Any
import aiohttp

logger: logging.Logger = logging.getLogger("FragmentBlockchain")


class TonBlockchainClient:
    def __init__(
        self,
        use_testnet: bool = True,
        api_key: str | None = None,
    ) -> None:
        subdomain: str = "testnet." if use_testnet else ""
        self._endpoint_url: str = f"https://{subdomain}toncenter.com/api/v2/"
        self._api_key: str | None = api_key
        self._session: aiohttp.ClientSession | None = None

    async def initialize(self) -> None:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "FragmentTradingAgent/1.0",
        }
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=12.0)
        self._session = aiohttp.ClientSession(
            base_url=self._endpoint_url,
            headers=headers,
            timeout=timeout,
            trust_env=True,
        )
        logger.info("Blockchain Client connected to RPC: %s", self._endpoint_url)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_address_state(self, address: str) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("Blockchain HTTP session not initialized")

        url: str = f"getAddressInformation?address={address}"
        try:
            response: aiohttp.ClientResponse
            async with self._session.get(url) as response:
                if response.status != 200:
                    return {
                        "state": "unknown",
                        "balance_ton": Decimal("0.0"),
                        "raw_balance": 0,
                    }

                payload: dict[str, Any] = await response.json()
                if not payload.get("ok", False):
                    return {
                        "state": "unknown",
                        "balance_ton": Decimal("0.0"),
                        "raw_balance": 0,
                    }

                result: dict[str, Any] = payload.get("result", {})
                raw_balance_str: str = str(result.get("balance", "0"))
                raw_balance: int = int(raw_balance_str) if raw_balance_str.isdigit() else 0
                balance_ton: Decimal = (Decimal(raw_balance) / Decimal("1000000000")).quantize(
                    Decimal("0.000000001")
                )
                account_state: str = str(result.get("state", "uninitialized"))

                return {
                    "state": account_state,
                    "balance_ton": balance_ton,
                    "raw_balance": raw_balance,
                }
        except Exception as err:
            logger.error("Failed fetching on-chain account state: %s", str(err))
            return {
                "state": "error",
                "balance_ton": Decimal("0.0"),
                "raw_balance": 0,
            }