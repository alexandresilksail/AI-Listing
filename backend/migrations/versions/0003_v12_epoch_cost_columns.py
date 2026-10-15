"""V1.2：任务 epoch 与成本追溯列

修订标识：0003_v12_epoch_cost_columns
父修订：0002_cost_usd_nullable
创建日期：2026-10-15

新增：
- listing_tasks.epoch / image_gen_tasks.epoch：任务版本号。
  每次提交/重试/恢复 +1；worker 终态条件写入（WHERE id=? AND epoch=?），
  防止超时后醒来的旧执行覆盖重试任务的结果。
- api_call_logs.cost_basis：estimated/actual/unknown，区分费用依据。
- api_call_logs.price_version：计费用价格表版本，便于追溯估算依据。

SQLite 下 ADD COLUMN 带默认值可直接执行，数据不受影响。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_v12_epoch_cost_columns"
down_revision = "0002_cost_usd_nullable"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """列存在性检查：迁移必须幂等（create_all 新建的库已含新列）。"""
    from sqlalchemy import inspect
    insp = inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    for table in ("listing_tasks", "image_gen_tasks"):
        if not _column_exists(table, "epoch"):
            op.add_column(table, sa.Column("epoch", sa.Integer(),
                                           nullable=False, server_default="0"))
    if not _column_exists("api_call_logs", "cost_basis"):
        op.add_column("api_call_logs",
                      sa.Column("cost_basis", sa.String(length=16),
                                nullable=False, server_default="estimated"))
    if not _column_exists("api_call_logs", "price_version"):
        op.add_column("api_call_logs",
                      sa.Column("price_version", sa.String(length=32),
                                nullable=False, server_default=""))


def downgrade() -> None:
    # SQLite 不支持 DROP COLUMN（3.35+ 才支持）；用 batch 重建保证兼容。
    with op.batch_alter_table("api_call_logs") as batch:
        batch.drop_column("price_version")
        batch.drop_column("cost_basis")
    for table in ("image_gen_tasks", "listing_tasks"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("epoch")
