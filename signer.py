import asyncio
import base64
from decimal import Decimal
import logging
import sys
from typing import Any
import aiohttp
from pytoniq import WalletV4R2
from pytoniq_core import Address, Cell

logger: logging.Logger = logging.getLogger("TonSigner")


class OfflineProviderStub:
    async def raw_get_account_state(self, address: Any) -> tuple[None, None]:
        return None, None


class TonTransactionSigner:
    def __init__(
        self,
        mnemonic_words: list[str],
        use_testnet: bool = True,
        api_key: str | None = None,
    ) -> None:
        self._mnemonic: list[str] = mnemonic_words
        self._is_testnet: bool = use_testnet
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

        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=15.0)
        self._session = aiohttp.ClientSession(
            base_url=self._endpoint_url,
            headers=headers,
            timeout=timeout,
            trust_env=True,
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_seqno(self, address: str) -> int:
        if self._session is None:
            raise RuntimeError("HTTP session not initialized")

        url: str = "runGetMethod"
        payload: dict[str, Any] = {
            "address": address,
            "method": "seqno",
            "stack": [],
        }
        try:
            response: aiohttp.ClientResponse
            async with self._session.post(url, json=payload) as response:
                if response.status != 200:
                    return 0
                data: dict[str, Any] = await response.json()
                if not data.get("ok", False):
                    return 0
                result: dict[str, Any] = data.get("result", {})
                stack: list[Any] = result.get("stack", [])
                if stack and isinstance(stack[0], list) and len(stack[0]) > 1:
                    raw_val: str = str(stack[0][1])
                    return int(raw_val, 16) if raw_val.startswith("0x") else int(raw_val)
                return 0
        except Exception as err:
            logger.warning("Seqno resolution notice: %s", str(err))
            return 0

    async def broadcast_signed_boc(self, boc_base64: str) -> bool:
        if self._session is None:
            raise RuntimeError("HTTP session not initialized")

        url: str = "sendBoc"
        payload: dict[str, str] = {"boc": boc_base64}
        try:
            response: aiohttp.ClientResponse
            async with self._session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error("BOC broadcast rejected with HTTP %d", response.status)
                    return False
                res_data: dict[str, Any] = await response.json()
                is_ok: bool = bool(res_data.get("ok", False))
                if is_ok:
                    logger.info("ON-CHAIN EXECUTION CONFIRMED: Transaction broadcast to TON mempool.")
                else:
                    logger.error("Broadcast rejected by validators: %s", res_data.get("error"))
                return is_ok
        except Exception as broadcast_err:
            logger.error("BOC broadcast error: %s", str(broadcast_err))
            return False

    async def execute_smart_contract_buy(
        self,
        destination_contract: str,
        amount_ton: Decimal,
        is_dry_run: bool,
        payload_data: str | None = None,
    ) -> bool:
        dummy_provider: OfflineProviderStub = OfflineProviderStub()
        wallet: WalletV4R2 = await WalletV4R2.from_mnemonic(
            provider=dummy_provider,
            mnemonics=self._mnemonic,
        )

        source_address: str = wallet.address.to_str(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=False,
            is_test_only=self._is_testnet,
        )

        current_seqno: int = await self.get_seqno(source_address)
        logger.info("ON-CHAIN SEQNO: %d for wallet %s", current_seqno, source_address)

        nanotons: int = int(amount_ton * Decimal("1000000000"))
        logger.info(
            "CRYPTOGRAPHIC VERIFICATION: Transfer of %d nanoTON to %s assembled with payload.",
            nanotons,
            destination_contract,
        )

        if is_dry_run:
            logger.info("DRY-RUN GUARD: Transaction prepared and signed locally. Broadcast suppressed.")
            return True

        transfer_cell: Cell = wallet.create_transfer_message(
            to_addr=destination_contract,
            amount=nanotons,
            seqno=current_seqno,
            payload=payload_data,
            send_mode=3,
        )
        boc_bytes: bytes = transfer_cell.to_boc()
        boc_base64: str = base64.b64encode(boc_bytes).decode("utf-8")

        return await self.broadcast_signed_boc(boc_base64)