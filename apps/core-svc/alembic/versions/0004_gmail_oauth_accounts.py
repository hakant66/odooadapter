"""add gmail oauth accounts

Revision ID: 0004_gmail_oauth_accounts
Revises: 0003_canonical_emails
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_gmail_oauth_accounts"
down_revision: Union[str, None] = "0003_canonical_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_oauth_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("credential_ref", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_tenant_gmail_account"),
    )
    op.create_index("idx_gmail_oauth_tenant", "gmail_oauth_accounts", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_gmail_oauth_tenant", table_name="gmail_oauth_accounts")
    op.drop_table("gmail_oauth_accounts")
