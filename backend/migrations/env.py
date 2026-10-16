import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool

from gutcare.activity import models as _activity_models  # noqa: F401
from gutcare.auth.models import Base
from gutcare.config import Settings
from gutcare.files import models as _file_models  # noqa: F401
from gutcare.medication import models as _medication_models  # noqa: F401
from gutcare.mood import models as _mood_models  # noqa: F401
from gutcare.privacy import models as _privacy_models  # noqa: F401

config = context.config
# Offline SQL rendering does not need logger handlers; avoid fileConfig's Windows
# stream initialization, which can fault before Alembic's static context is created.
if (
    config.config_file_name is not None
    and not context.is_offline_mode()
    and not config.attributes.get("skip_file_config", False)
):
    fileConfig(config.config_file_name)

repository_env = Path(__file__).resolve().parents[2] / ".env"
configured_url = Settings(_env_file=repository_env).database_url
repository_values = dotenv_values(repository_env)
database_url = (
    os.environ.get("MIGRATOR_DATABASE_URL")
    or repository_values.get("MIGRATOR_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or (str(configured_url) if configured_url is not None else None)
)
if database_url:
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
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
        context.configure(
            connection=connection, target_metadata=target_metadata, include_schemas=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
