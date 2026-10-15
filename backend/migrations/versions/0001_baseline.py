"""baseline：全表基线（等价于 Base.metadata.create_all）

修订标识：0001_baseline
父修订：None
创建日期：2026-10-15

说明：V1.0 及更早版本的数据库由 create_all() 直接建表，没有版本记录。
本基线用 create_all 幂等建全部表（已存在的表不受影响）。
对已存在的旧库执行 `alembic stamp 0001_baseline` 即可标记基线，
后续变更由 0002/0003 等增量迁移完成。
"""
from __future__ import annotations

from alembic import op

from app.database import Base
from app import models  # noqa: F401  确保全部模型已注册

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    # 基线不提供降级（删全部表风险过高，生产禁止）
    raise NotImplementedError("基线迁移不支持降级")
