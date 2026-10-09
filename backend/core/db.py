from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def close_db() -> None:
    await engine.dispose()
