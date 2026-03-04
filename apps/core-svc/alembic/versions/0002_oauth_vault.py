"""oauth and credential vault

Revision ID: 0002_oauth_vault
Revises: 0001_initial
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_oauth_vault"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credential_vault",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("connector", sa.String(length=50), nullable=False),
        sa.Column("secret_type", sa.String(length=50), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_credential_vault_tenant_connector",
        "credential_vault",
        ["tenant_id", "connector"],
    )

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("connector", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", name="uq_oauth_state"),
    )
    op.create_index("idx_oauth_state_expiry", "oauth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_oauth_state_expiry", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("idx_credential_vault_tenant_connector", table_name="credential_vault")
    op.drop_table("credential_vault")
