from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db

class Wallet(db.Model):
    __tablename__ = 'wallets'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0.00'))
    currency = db.Column(db.String(10), nullable=False, default='INR')
    status = db.Column(db.String(30), nullable=False, default='active') # active, frozen
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    transactions = db.relationship('WalletTransaction', backref='wallet', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Wallet CompanyID: {self.company_id} Balance: {self.currency} {self.balance}>"
