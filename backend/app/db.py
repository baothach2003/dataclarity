"""Engine and session factory, built from Settings.database_url."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    # Lazy: no connection is opened until the first query, so the app starts
    # even while the database is down. pool_pre_ping replaces connections a
    # restarted PostgreSQL has dropped.
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
