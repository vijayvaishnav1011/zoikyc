from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db

class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'

    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True)
    type = db.Column(db.String(30), nullable=False) # credit, debit
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    balance_before = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=False)
    reference_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default='success') # success, pending, failed
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<WalletTransaction {self.reference_id} Type: {self.type} Amount: {self.amount}>"
