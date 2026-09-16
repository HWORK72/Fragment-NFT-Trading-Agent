import asyncio
from decimal import Decimal
import os
from typing import Any
from bs4 import BeautifulSoup
import pytest
from blockchain import TonBlockchainClient
from database import MarketTick, TradeDecision
from main import (
    AgentSettings,
    BackdropClassifier,
    GiftAuction,
    MarketAnalyzer,
    MarketMetrics,
    RiskManager,
)
from signer import TonTransactionSigner


def test_backdrop_classifier_positive() -> None:
    black_samples: list[str] = [
        "Onyx Black",
        "Obsidian",
        "Pitch Black",
        "Charcoal Night",
        "Dark Obsidian",
        "Черный оникс",
    ]
    sample: str
    for sample in black_samples:
        assert BackdropClassifier.is_black(sample) is True


def test_backdrop_classifier_negative() -> None:
    common_samples: list[str] = [
        "Emerald Green",
        "Sapphire Blue",
        "Neon Violet",
        "Standard",
        "Aquamarine",
    ]
    sample: str
    for sample in common_samples:
        assert BackdropClassifier.is_black(sample) is False


def test_market_analyzer_trimmed_mean() -> None:
    analyzer: MarketAnalyzer = MarketAnalyzer()
    prices: list[Decimal] = [
        Decimal("10.0"),
        Decimal("10.5"),
        Decimal("11.0"),
        Decimal("10.8"),
        Decimal("11.2"),
        Decimal("10.0"),
        Decimal("10.2"),
        Decimal("10.9"),
        Decimal("11.1"),
        Decimal("10.5"),
        Decimal("500.0"),
    ]
    price: Decimal
    for price in prices:
        analyzer.record_price("homemadecake", False, price)

    metrics: MarketMetrics | None = analyzer.get_metrics("homemadecake", False)
    assert metrics is not None
    assert metrics.floor_price == Decimal("10.0")
    assert metrics.average_price < Decimal("15.0")
    assert metrics.sample_size == len(prices)


def test_risk_manager_balance_breach() -> None:
    settings: AgentSettings = AgentSettings(
        ton_wallet_balance=Decimal("2.0"),
        min_balance_reserve_ton=Decimal("0.5"),
        max_bid_per_item_ton=Decimal("15.0"),
    )
    risk_manager: RiskManager = RiskManager(settings)

    expensive_item: GiftAuction = GiftAuction(
        auction_id="test_1",
        title="Cake No. 1",
        model="homemadecake",
        gift_num=1,
        backdrop="Standard",
        is_black_backdrop=False,
        current_bid=Decimal("10.0"),
        bid_step=Decimal("1.0"),
        ends_at=metrics_time(),
        highest_bidder_is_me=False,
        url="https://fragment.com/gift/test_1",
        is_active=True,
        is_live_data=True,
    )

    approved: bool
    reason: str
    approved, reason = risk_manager.validate_trade_opportunity(expensive_item, Decimal("12.0"))
    assert approved is False
    assert "Balance reserve breach" in reason


def test_html_fixture_parsing() -> None:
    assert os.path.exists("fragment_debug.html") is True
    with open("fragment_debug.html", "r", encoding="utf-8") as file:
        html_content: str = file.read()

    soup: BeautifulSoup = BeautifulSoup(html_content, "lxml")
    cards: list[Any] = soup.select(".tm-grid-item")
    assert len(cards) > 0

    first_card: Any = cards[0]
    name_elem: Any = first_card.select_one(".item-name")
    assert name_elem is not None
    assert "Homemade Cake" in name_elem.get_text(strip=True)


@pytest.mark.asyncio
async def test_crypto_signer_seqno_query() -> None:
    words: list[str] = os.getenv(
        "TON_WALLET_MNEMONIC",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon art",
    ).strip().replace('"', '').split()

    signer: TonTransactionSigner = TonTransactionSigner(words)
    await signer.initialize()
    try:
        seqno: int = await signer.get_seqno("0QDwnisxeXetFMi28eQX6I_ZLAvvAisjLyWl-_PmGoAHrOFA")
        assert isinstance(seqno, int) is True
        assert seqno >= 0
    finally:
        await signer.close()


def metrics_time() -> Any:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)