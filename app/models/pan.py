import json
from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db

class PANVerification(db.Model):
    __tablename__ = 'pan_verifications'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Inputs
    pan_number = db.Column(db.String(20), nullable=False, index=True)
    dob = db.Column(db.String(20), nullable=True, default='') # Optional for GetPANStatus

    # Verification Outcomes
    status = db.Column(db.String(50), nullable=False, default='pending') # verified, failed, invalid
    status_message = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(100), nullable=True)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(100), nullable=True) # Individual, Company, Firm, etc.
    pan_status = db.Column(db.String(50), nullable=True) # VALID, ACTIVE, OPERATIVE
    dob_match = db.Column(db.Boolean, nullable=True)
    aadhaar_seeding_status = db.Column(db.String(100), nullable=True) # Linked, Not Linked, N/A

    # Cost & Billing
    cost_charged = db.Column(db.Numeric(10, 2), nullable=True, default=Decimal('0.00'))

    # Raw Payload & Reference
    reference_id = db.Column(db.String(100), nullable=True, index=True)
    raw_request = db.Column(db.Text, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    company = db.relationship('Company', backref=db.backref('pan_verifications', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('pan_verifications', lazy='dynamic'))

    @property
    def response_dict(self):
        if not self.raw_response:
            return {}
        try:
            return json.loads(self.raw_response)
        except Exception:
            return {}

    def __repr__(self):
        return f"<PANVerification {self.pan_number} - {self.status}>"
