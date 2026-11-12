from datetime import datetime, timezone
from decimal import Decimal
from typing import Final
from src.fragment_agent.models import MarketMetrics


class BackdropClassifier:
    BLACK_KEYWORDS: Final[tuple[str, ...]] = (
        "black",
        "onyx",
        "obsidian",
        "pitch",
        "charcoal",
        "night",
        "dark",
        "ebony",
        "raven",
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

        total_sum: Decimal = sum(calc_prices, Decimal("0"))
        avg_val: Decimal = total_sum / Decimal(str(len(calc_prices)))

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

    def get_fair_value(
        self,
        model: str,
        is_black: bool,
        candidate_price: Decimal | None = None,
    ) -> Decimal | None:
        key: tuple[str, bool] = (model.lower(), is_black)
        prices: list[Decimal] = sorted(self._price_history.get(key, []))
        if not prices:
            return None

        if candidate_price is not None and len(prices) >= 2:
            reference_pool: list[Decimal] = list(prices)
            if candidate_price in reference_pool:
                reference_pool.remove(candidate_price)
            if reference_pool:
                return reference_pool[0].quantize(Decimal("0.01"))

        return prices[0].quantize(Decimal("0.01"))