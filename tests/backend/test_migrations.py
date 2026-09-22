from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

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


FIRST_REVISION = "2a9492d9af49"


def insert_run(connection: Connection, status: str) -> None:
    connection.execute(
        text(
            "INSERT INTO runs (id, filename, size_bytes, status, created_at, expires_at)"
            " VALUES ('11111111-1111-4111-8111-111111111111', 'a.csv', 1, :status,"
            " '2026-09-22', '2026-09-23')"
        ),
        {"status": status},
    )


def test_the_claim_status_is_accepted_after_the_second_migration(engine: Engine) -> None:
    with engine.begin() as connection:
        migrate(connection, "head")
        insert_run(connection, "cleaning")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM runs")).scalar_one() == "cleaning"


def test_the_first_revision_does_not_know_the_claim_status(engine: Engine) -> None:
    # Guards the test above: it must not pass just because nothing checks the column.
    with engine.begin() as connection:
        migrate(connection, FIRST_REVISION)
        with pytest.raises(IntegrityError, match="CHECK"):
            insert_run(connection, "cleaning")


def test_the_constraint_still_rejects_an_unknown_status_at_head(engine: Engine) -> None:
    with engine.begin() as connection:
        migrate(connection, "head")
        with pytest.raises(IntegrityError, match="CHECK"):
            insert_run(connection, "bogus")

    names = {c["name"] for c in inspect(engine).get_check_constraints("runs")}
    assert names == {"ck_runs_run_status"}


def test_downgrading_puts_a_run_being_cleaned_back_to_planned(engine: Engine) -> None:
    # Nothing can be executing while the schema is downgraded, and the old
    # constraint would refuse the row, so the migration must move it.
    with engine.begin() as connection:
        migrate(connection, "head")
        insert_run(connection, "cleaning")
        migrate(connection, FIRST_REVISION, downgrade=True)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM runs")).scalar_one() == "planned"
