import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import random
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup
from src.fragment_agent.analyzer import BackdropClassifier
from src.fragment_agent.config import AgentSettings
from src.fragment_agent.logger import get_logger
from src.fragment_agent.models import GiftAuction

logger: logging.Logger = get_logger("FragmentScraper")


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