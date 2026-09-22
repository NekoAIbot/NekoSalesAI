"""Revision: add auth token tables

The email-verification and password-reset models were added with the auth
service, but no migration created their tables — the model metadata and the
migrated database drifted apart, so a fresh ``alembic upgrade head`` produced
a database the application could not fully use.
"""

revision: str = "a1b2c3d4e5f6"
down_revision: str = "b7c2d4e5f6a7"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Guards because the live database already has these tables: they were
    # created by the app's create_all at startup, outside Alembic, when the
    # auth models landed without a migration. A fresh clone (and the
    # migration test) still gets them created here.
    from sqlalchemy import inspect

    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())

    if "email_verification_codes" not in existing:
        op.create_table(
            "email_verification_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code_hash", sa.String(length=255), nullable=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "expires_at", sa.DateTime(timezone=True), nullable=False
            ),
            sa.Column("attempts", sa.Integer(), nullable=True, default=0),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )

    if "password_reset_tokens" not in existing:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token_hash", sa.String(length=255), nullable=True, unique=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "expires_at", sa.DateTime(timezone=True), nullable=False
            ),
            sa.Column("used", sa.Boolean(), nullable=True, default=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_codes")
