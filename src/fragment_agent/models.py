from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


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
