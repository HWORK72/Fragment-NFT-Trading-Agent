from datetime import datetime, timezone
from decimal import Decimal
import logging
from pathlib import Path
from typing import Any, Final
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from src.fragment_agent.logger import BASE_DIR, get_logger

logger: logging.Logger = get_logger("FragmentDB")

DB_FILE_PATH: Final[Path] = BASE_DIR / "fragment_market.db"
DATABASE_URL: Final[str] = f"sqlite+aiosqlite:///{DB_FILE_PATH}"

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
    logger.info("Database schema verified and operational: %s", DB_FILE_PATH.name)


async def bulk_record_market_ticks(ticks_data: list[dict[str, Any]]) -> None:
    if not ticks_data:
        return
    async with async_session_factory() as session:
        try:
            records: list[MarketTick] = [
                MarketTick(
                    collection=str(item["collection"]),
                    gift_num=int(item["gift_num"]),
                    price_ton=Decimal(str(item["price_ton"])),
                    is_black_backdrop=bool(item["is_black_backdrop"]),
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
                    auction_id=str(item["auction_id"]),
                    collection=str(item["collection"]),
                    price_ton=Decimal(str(item["price_ton"])),
                    floor_at_execution=Decimal(str(item["floor_at_execution"])),
                    verdict=str(item["verdict"]),
                    reason=str(item["reason"]),
                )
                for item in decisions_data
            ]
            session.add_all(records)
            await session.commit()
        except Exception as err:
            await session.rollback()
            logger.error("Failed batch recording decisions: %s", str(err))