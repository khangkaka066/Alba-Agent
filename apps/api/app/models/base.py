"""Common SQLAlchemy mapping primitives."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata root for all control-plane tables."""


class ScopedRow:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def scope_constraints(table: str) -> tuple[ForeignKeyConstraint, UniqueConstraint]:
    return (
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["workspaces.tenant_id", "workspaces.id"],
            name=f"fk_{table}_workspace_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "workspace_id", "id", name=f"uq_{table}_scope_id"),
    )


def scoped_reference(table: str, target: str, column: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "workspace_id", column],
        [f"{target}.tenant_id", f"{target}.workspace_id", f"{target}.id"],
        name=f"fk_{table}_{column}_scope",
        ondelete="CASCADE",
    )
