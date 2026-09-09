from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings.ensure_dirs()
        url = f"sqlite:///{settings.db_path}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s


def get_session() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s
