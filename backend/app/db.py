"""SQLite engine and session. Foreign keys are switched on for every connection."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH


class Base(DeclarativeBase):
    pass


def make_engine(path=DB_PATH):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(eng=None) -> None:
    from . import models  # noqa: F401  (registers tables)

    eng = eng or engine
    Base.metadata.create_all(eng)
    _add_missing_columns(eng)


def _add_missing_columns(eng) -> None:
    """Tiny migration: add columns introduced in later builds to an existing database.

    create_all() makes new tables but never changes old ones, so a planner.db made by
    an earlier build would lack new columns. Every added column is nullable or has a default.
    """
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(eng.dialect)}'
                default = getattr(col.default, "arg", None)
                if isinstance(default, (str, int, float, bool)):
                    ddl += f" DEFAULT {repr(default) if isinstance(default, str) else int(default) if isinstance(default, bool) else default}"
                conn.execute(text(ddl))
            for idx in table.indexes:
                cols = ", ".join(c.name for c in idx.columns)
                unique = "UNIQUE " if idx.unique else ""
                conn.execute(text(f"CREATE {unique}INDEX IF NOT EXISTS {idx.name} ON {table.name} ({cols})"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
