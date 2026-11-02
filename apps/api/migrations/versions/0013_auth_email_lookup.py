"""Index normalized account email for public signup and login.

Revision ID: 0013_auth_email_lookup
Revises: 0012_skills_and_builtin_tools
"""

from alembic import op

revision = "0013_auth_email_lookup"
down_revision = "0012_skills_and_builtin_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_users_email_lookup", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email_lookup", table_name="users")
