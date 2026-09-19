from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, create_engine, inspect

from app.config import REPO_ROOT
from app.models import Base

ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    # A file, not :memory:, so every connection sees the same database.
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    yield engine
    engine.dispose()


def migrate(connection: Connection, target: str, downgrade: bool = False) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = connection
    if downgrade:
        command.downgrade(config, target)
    else:
        command.upgrade(config, target)


def test_upgrade_creates_the_runs_table_with_the_specs_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        migrate(connection, "head")

    columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    # SPECS section 9, exactly: no invented columns.
    assert columns == {
        "id", "filename", "size_bytes", "status", "created_at", "expires_at", "error_code",
    }


def test_migrated_schema_matches_the_models(engine: Engine) -> None:
    with engine.begin() as connection:
        migrate(connection, "head")

    with engine.connect() as connection:
        drift = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert drift == []


def test_downgrade_removes_everything_and_upgrade_works_again(engine: Engine) -> None:
    with engine.begin() as connection:
        migrate(connection, "head")
        migrate(connection, "base", downgrade=True)
    assert "runs" not in inspect(engine).get_table_names()

    with engine.begin() as connection:
        migrate(connection, "head")
    assert "runs" in inspect(engine).get_table_names()


def test_status_check_constraint_has_the_convention_name(engine: Engine) -> None:
    # Autogenerate does not compare CHECK constraints, so the drift test above
    # cannot catch a differently named constraint; later migrations that alter
    # it depend on the name being the same everywhere.
    with engine.begin() as connection:
        migrate(connection, "head")

    names = {c["name"] for c in inspect(engine).get_check_constraints("runs")}
    assert names == {"ck_runs_run_status"}
