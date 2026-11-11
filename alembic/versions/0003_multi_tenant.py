"""Multi-tenant: add organizations, org_api_keys tables and org_id FKs

Revision ID: 0003_multi_tenant
Revises: 0002_webhooks
Create Date: 2026-11-11 11:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_multi_tenant"
down_revision: Union[str, None] = "0002_webhooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── organizations ──────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"])

    # ── org_api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        "org_api_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_org_api_keys_key_hash"),
    )
    op.create_index("ix_org_api_keys_org_id", "org_api_keys", ["org_id"])
    op.create_index("ix_org_api_keys_key_prefix", "org_api_keys", ["key_prefix"])

    # ── Add org_id FK to existing tables ───────────────────────────────────────
    # NOTE: In a production migration you would need to backfill org_id for
    # existing rows. For a fresh v0.5.0 install these tables are empty.

    op.add_column(
        "policies",
        sa.Column("org_id", sa.String(36), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        "fk_policies_org_id", "policies", "organizations",
        ["org_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_policies_org_id", "policies", ["org_id"])

    op.add_column(
        "agents",
        sa.Column("org_id", sa.String(36), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        "fk_agents_org_id", "agents", "organizations",
        ["org_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_agents_org_id", "agents", ["org_id"])

    op.add_column(
        "audit_log",
        sa.Column("org_id", sa.String(36), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        "fk_audit_log_org_id", "audit_log", "organizations",
        ["org_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"])

    op.add_column(
        "webhooks",
        sa.Column("org_id", sa.String(36), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        "fk_webhooks_org_id", "webhooks", "organizations",
        ["org_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])


def downgrade() -> None:
    # Remove org_id from existing tables
    op.drop_index("ix_webhooks_org_id", table_name="webhooks")
    op.drop_constraint("fk_webhooks_org_id", "webhooks", type_="foreignkey")
    op.drop_column("webhooks", "org_id")

    op.drop_index("ix_audit_log_org_id", table_name="audit_log")
    op.drop_constraint("fk_audit_log_org_id", "audit_log", type_="foreignkey")
    op.drop_column("audit_log", "org_id")

    op.drop_index("ix_agents_org_id", table_name="agents")
    op.drop_constraint("fk_agents_org_id", "agents", type_="foreignkey")
    op.drop_column("agents", "org_id")

    op.drop_index("ix_policies_org_id", table_name="policies")
    op.drop_constraint("fk_policies_org_id", "policies", type_="foreignkey")
    op.drop_column("policies", "org_id")

    # Drop new tables
    op.drop_table("org_api_keys")
    op.drop_table("organizations")
