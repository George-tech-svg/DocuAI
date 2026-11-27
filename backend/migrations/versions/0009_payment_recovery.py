"""Add manual M-Pesa payment recovery requests and administrator audit logs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "payment_recovery_requests",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mpesa_message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("matched_payment_id", uuid, sa.ForeignKey("mpesa_payments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_subscription_id", uuid, sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending', 'granted', 'rejected')", name="ck_payment_recovery_status"),
    )
    op.create_index("ix_payment_recovery_requests_user_id", "payment_recovery_requests", ["user_id"])
    op.create_index("ix_payment_recovery_requests_paid_at", "payment_recovery_requests", ["paid_at"])
    op.create_index("ix_payment_recovery_requests_status", "payment_recovery_requests", ["status"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("admin_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_recovery_request_id", uuid, sa.ForeignKey("payment_recovery_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_logs_admin_user_id", "admin_audit_logs", ["admin_user_id"])
    op.create_index("ix_admin_audit_logs_payment_recovery_request_id", "admin_audit_logs", ["payment_recovery_request_id"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_payment_recovery_request_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_payment_recovery_requests_status", table_name="payment_recovery_requests")
    op.drop_index("ix_payment_recovery_requests_paid_at", table_name="payment_recovery_requests")
    op.drop_index("ix_payment_recovery_requests_user_id", table_name="payment_recovery_requests")
    op.drop_table("payment_recovery_requests")
