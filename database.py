import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger: logging.Logger = logging.getLogger("FragmentDB")

DATABASE_URL: str = "sqlite+aiosqlite:///fragment_market.db"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


class MarketTick(Base):
    __tablename__: str = "market_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection: Mapped[str] = mapped_column(String(64), index=True)
    gift_num: Mapped[int] = mapped_column(Integer, index=True)
    price_ton: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_black_backdrop: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class TradeDecision(Base):
    __tablename__: str = "trade_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auction_id: Mapped[str] = mapped_column(String(64), index=True)
    collection: Mapped[str] = mapped_column(String(64))
    price_ton: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    floor_at_execution: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("Database schema verified and operational: fragment_market.db")


async def bulk_record_market_ticks(ticks_data: list[dict[str, Any]]) -> None:
    if not ticks_data:
        return
    async with async_session_factory() as session:
        try:
            records: list[MarketTick] = [
                MarketTick(
                    collection=item["collection"],
                    gift_num=item["gift_num"],
                    price_ton=item["price_ton"],
                    is_black_backdrop=item["is_black_backdrop"],
                )
                for item in ticks_data
            ]
            session.add_all(records)
            await session.commit()
        except Exception as err:
            await session.rollback()
            logger.error("Failed batch recording ticks: %s", str(err))


async def bulk_record_trade_decisions(decisions_data: list[dict[str, Any]]) -> None:
    if not decisions_data:
        return
    async with async_session_factory() as session:
        try:
            records: list[TradeDecision] = [
                TradeDecision(
                    auction_id=item["auction_id"],
                    collection=item["collection"],
                    price_ton=item["price_ton"],
                    floor_at_execution=item["floor_at_execution"],
                    verdict=item["verdict"],
                    reason=item["reason"],
                )
                for item in decisions_data
            ]
            session.add_all(records)
            await session.commit()
        except Exception as err:
            await session.rollback()
            logger.error("Failed batch recording decisions: %s", str(err))