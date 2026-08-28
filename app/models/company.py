from datetime import datetime, timezone
from app.extensions import db

class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    authorised_signatory_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(100), nullable=False, default='India')
    state = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    gstin = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='active') # active, pending_verification, suspended
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    users = db.relationship('User', backref='company', lazy='dynamic', cascade='all, delete-orphan')
    wallet = db.relationship('Wallet', backref='company', uselist=False, cascade='all, delete-orphan')
    transactions = db.relationship('WalletTransaction', backref='company', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('CompanyDocument', backref='company', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Company {self.name} (ID: {self.id})>"
