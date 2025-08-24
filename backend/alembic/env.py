from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa tu Base y modelos para autogenerate
from app.db import Base
from app.config import get_settings
from app.models.load import Load
from app.models.apsa_protocol import ApsaProtocol
from app.models.aconex_doc import AconexDoc
from app.models.user import User
from app.models.refresh_token import RefreshToken

# Config Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    settings = get_settings()
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    settings = get_settings()
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()