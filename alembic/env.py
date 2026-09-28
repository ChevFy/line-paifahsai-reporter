from logging.config import fileConfig

from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

from alembic import context
from config.config import settings
from models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

POSTGIS_SCHEMAS = {"tiger", "tiger_data", "topology"}
POSTGIS_TABLES = {"spatial_ref_sys"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name in POSTGIS_TABLES:
        return False
    if getattr(obj, "schema", None) in POSTGIS_SCHEMAS:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def configure_kwargs() -> dict:
    return {
        "target_metadata": target_metadata,
        "include_object": include_object,
        "process_revision_directives": alembic_helpers.writer,
        "render_item": alembic_helpers.render_item,
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, **configure_kwargs())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
