import os

import pytest

TEST_ENV = {
    "LINE_CHANNEL_SECRET": "test-secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "test-access-token",
    "LINE_LOGIN_CHANNEL_ID": "test-login-channel",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "test",
    "LIFF_ALLOWED_ORIGINS": '["https://liff.example"]',
    "S3_ENDPOINT_URL": "http://127.0.0.1:8333",
    "S3_REGION": "us-east-1",
    "S3_ACCESS_KEY": "test-access-key",
    "S3_SECRET_KEY": "test-secret-key",
    "S3_BUCKET": "test-bucket",
    "PUBLIC_BASE_URL": "https://paifahsai.example",
    "PHOTO_LINK_SECRET": "test-photo-link-secret-0123456789abcdef",
}

for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

PAI = "5803"
MAE_TAENG = "5006"

requires_postgis = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (needs PostgreSQL + PostGIS)",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def schema():
    import sqlalchemy as sa
    from sqlalchemy.pool import NullPool

    from models import Base

    engine = sa.create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    yield engine
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
    engine.dispose()


@pytest.fixture
async def sessionmaker(schema):
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from models import Base, District

    with schema.begin() as connection:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        connection.execute(
            sa.insert(District).values(
                [
                    {"code": PAI, "name_th": "ปาย", "province_name_th": "แม่ฮ่องสอน"},
                    {
                        "code": MAE_TAENG,
                        "name_th": "แม่แตง",
                        "province_name_th": "เชียงใหม่",
                    },
                ]
            )
        )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
