"""school plus staff id is the local account key

Revision ID: 20261105_0003
Revises: 20260909_0002
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0003"
down_revision: Union[str, Sequence[str], None] = "20260909_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_identities",
        sa.Column("school", sa.String(80), nullable=False, server_default=""),
    )
    op.add_column(
        "user_profiles",
        sa.Column("school", sa.String(80), nullable=False, server_default=""),
    )
    op.drop_constraint(
        "uq_auth_identities_provider_subject",
        "auth_identities",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_auth_identities_provider_school_subject",
        "auth_identities",
        ["provider", "school", "subject"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_auth_identities_provider_school_subject",
        "auth_identities",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_auth_identities_provider_subject",
        "auth_identities",
        ["provider", "subject"],
    )
    op.drop_column("user_profiles", "school")
    op.drop_column("auth_identities", "school")
