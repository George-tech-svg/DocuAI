"""Add subscription plan, subscription, and M-Pesa payment records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    uuid = postgresql.UUID(as_uuid=True)
    if "subscription_plans" not in tables:
        op.create_table(
            "subscription_plans",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("price_kes", sa.Integer(), nullable=False),
            sa.Column("duration_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if "subscriptions" not in tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("plan_id", uuid, sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
        op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
        op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])
    if "mpesa_payments" not in tables:
        op.create_table(
            "mpesa_payments",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("subscription_id", uuid, sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("amount_kes", sa.Integer(), nullable=False),
            sa.Column("phone_number", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("callback_token", sa.String(64), nullable=False, unique=True),
            sa.Column("checkout_request_id", sa.String(100), nullable=True, unique=True),
            sa.Column("merchant_request_id", sa.String(100), nullable=True),
            sa.Column("mpesa_receipt", sa.String(40), nullable=True, unique=True),
            sa.Column("result_code", sa.Integer(), nullable=True),
            sa.Column("result_description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_mpesa_payments_user_id", "mpesa_payments", ["user_id"])
        op.create_index("ix_mpesa_payments_subscription_id", "mpesa_payments", ["subscription_id"])
        op.create_index("ix_mpesa_payments_status", "mpesa_payments", ["status"])
        op.create_index("ix_mpesa_payments_callback_token", "mpesa_payments", ["callback_token"])


def downgrade():
    # Preserve financial records if an application rollback is required.
    pass
