"""cost_usd 可空化：支持「未知费用」三态（V1.1）

修订标识：0002_cost_usd_nullable
父修订：0001_baseline
创建日期：2026-10-15

背景：V1.0 的 cost_usd 为 NOT NULL，未知模型价格只能按 0 计——
系统性低估成本。V1.1 起改为 nullable：NULL=费用未知，
配合 cost_known 标志与 today_unknown_cost_calls 统计。

SQLite 不支持 ALTER COLUMN，使用 batch 模式重建表（数据保留）。
PostgreSQL 下 batch 同样安全。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_cost_usd_nullable"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_TABLES = ("listing_tasks", "image_gen_tasks", "api_call_logs")


def _cost_usd_nullable(table: str) -> bool:
    """cost_usd 是否已可空（create_all 新建的库已满足则跳过）。"""
    from sqlalchemy import inspect
    insp = inspect(op.get_bind())
    for c in insp.get_columns(table):
        if c["name"] == "cost_usd":
            return bool(c["nullable"])
    return True  # 列不存在（全新库由 baseline 建为可空）


def upgrade() -> None:
    for table in _TABLES:
        if not _cost_usd_nullable(table):
            with op.batch_alter_table(table) as batch:
                batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # 降级会把未知费用（NULL）改写为 0——与设计相悖，且可能静默低估成本。
    # 仅在明确知晓风险时使用：先把 NULL 行处理掉再降级。
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=False,
                               server_default="0")
