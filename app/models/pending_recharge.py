from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db


class PendingRecharge(db.Model):
    """
    Tracks Razorpay orders that have been created but not yet confirmed.
    Used for reconciliation: if a user's payment goes through but the callback
    fails, this record allows us to recover and credit the wallet.
    """
    __tablename__ = 'pending_recharges'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    razorpay_order_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    base_amount = db.Column(db.Numeric(12, 2), nullable=False)       # Amount to credit to wallet
    platform_fee = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0.00'))
    total_payable = db.Column(db.Numeric(12, 2), nullable=False)     # Amount user was charged (base + fee)

    # Status lifecycle: pending -> captured / failed / expired
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)

    # Set when payment is captured or failed
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return (
            f"<PendingRecharge order={self.razorpay_order_id} "
            f"company={self.company_id} status={self.status}>"
        )
