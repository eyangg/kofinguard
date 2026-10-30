from logging.config import fileConfig

from alembic import context

# alembic.ini의 prepend_sys_path로 backend 폴더가 import 경로에 들어 있다.
import db
import models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = models.Base.metadata


def _database_url() -> str:
    # DATABASE_URL이 없으면 SQLite로 넘어가지 않고 여기서 멈춘다.
    db.load_env()
    return db.get_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=db.resolve_url(_database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = db.make_engine(_database_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite는 ALTER가 제한적이라 batch 모드로 만든다.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
