"""数据库连接与会话管理（SQLite 开发环境，支持迁移 PostgreSQL）。"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import effective_settings

logger = logging.getLogger("polylisting.db")

_engine = None
_SessionLocal: sessionmaker[Session] | None = None

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


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
    """建表（开发期直接建表；生产使用 Alembic 迁移，见 migrations/）。

    create_all 只创建缺失的表，绝不修改已存在表的结构——
    结构变更必须走 apply_migrations()（Alembic）。
    """
    from . import models  # noqa: F401  确保模型已注册
    eng = get_engine()
    Base.metadata.create_all(eng)


def apply_migrations() -> dict:
    """运行 Alembic 增量迁移（upgrade head）。

    安全约定：
    - 迁移前自动备份 SQLite 文件（<db>.bak-<时间戳>）
    - 迁移失败：alembic 事务回滚（SQLite DDL 具事务性），备份保留，
      抛出 RuntimeError 阻止启动——绝不自动清空或重建数据库
    返回 {"backup": 路径或 None, "revision": "head"}。
    """
    import sys

    from alembic import command
    from alembic.config import Config

    url = effective_settings().database_url
    backup: Path | None = None
    if url.startswith("sqlite"):
        # sqlite:////abs/path 或 sqlite:///rel/path
        raw = url.split("///", 1)[-1]
        db_file = Path(raw)
        if not db_file.is_absolute():
            db_file = BASE_DIR / raw
        if db_file.exists():
            backup = db_file.with_name(
                f"{db_file.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
            shutil.copy2(db_file, backup)
            logger.info("迁移前已备份数据库：%s", backup)

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.upgrade(cfg, "head")
    except Exception as e:  # noqa: BLE001
        logger.exception("数据库迁移失败（已回滚，备份保留在 %s）：%s", backup, e)
        raise RuntimeError(
            f"数据库迁移失败：{e}。数据库已回滚且未做任何清空操作；"
            f"备份文件：{backup or '（新库无备份）'}。"
            "请检查 migrations/ 后重试，或手动执行 alembic upgrade head 查看详情。"
        ) from e
    logger.info("数据库迁移完成（head）")
    return {"backup": str(backup) if backup else None, "revision": "head"}


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
