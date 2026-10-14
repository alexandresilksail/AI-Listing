"""数据库连接与会话管理（SQLite 开发环境，支持迁移 PostgreSQL）。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import effective_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


def _make_engine():
    global _engine, _SessionLocal
    url = effective_settings().database_url
    connect_args = {}
    poolclass = None
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in url:
            poolclass = StaticPool
    _engine = create_engine(
        url,
        connect_args=connect_args,
        poolclass=poolclass,
        echo=False,
        future=True,
    )
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _fk_on(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """建表（开发期直接建表；生产使用 Alembic 迁移，见 migrations/）。"""
    from . import models  # noqa: F401  确保模型已注册
    eng = get_engine()
    Base.metadata.create_all(eng)


def get_engine():
    if _engine is None:
        _make_engine()
    assert _engine is not None
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    if _SessionLocal is None:
        _make_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    sm = get_sessionmaker()
    db = sm()
    try:
        yield db
    finally:
        db.close()
