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

    # Raw Payload, Network & Audit Logs
    reference_id = db.Column(db.String(100), nullable=True, index=True)
    raw_request = db.Column(db.Text, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    server_ip = db.Column(db.String(100), nullable=True, default='187.127.139.6', index=True) # Outbound VPS IP
    ip_address = db.Column(db.String(100), nullable=True, index=True) # Initiating client IP
    method = db.Column(db.String(100), nullable=True)     # e.g. CVL REST V2.6 / CVL SOAP V6.0
    endpoint = db.Column(db.String(255), nullable=True)   # e.g. /services/pan or /api/pan
    user_agent = db.Column(db.String(255), nullable=True) # Browser or API client
    duration_ms = db.Column(db.Integer, nullable=True)    # API execution time in ms

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
            return {"raw": self.raw_response}

    @property
    def request_dict(self):
        if not self.raw_request:
            return {}
        try:
            return json.loads(self.raw_request)
        except Exception:
            return {"raw": self.raw_request}

    def to_dict(self):
        user_info = None
        if self.user:
            user_info = {
                "id": self.user.id,
                "name": f"{self.user.first_name or ''} {self.user.last_name or ''}".strip() or self.user.email,
                "email": self.user.email,
                "role": self.user.role if hasattr(self.user, 'role') else 'user'
            }

        company_info = None
        if self.company:
            company_info = {
                "id": self.company.id,
                "name": self.company.name,
                "client_id": self.company.client_id or f"ZOI-{self.company.id}",
                "pos_code": self.company.pos_code
            }

        return {
            "id": self.id,
            "pan_number": self.pan_number,
            "dob": self.dob or "-",
            "status": self.status,
            "status_message": self.status_message or "",
            "full_name": self.full_name or "-",
            "first_name": self.first_name or "",
            "middle_name": self.middle_name or "",
            "last_name": self.last_name or "",
            "category": self.category or "Individual",
            "pan_status": self.pan_status or "-",
            "dob_match": self.dob_match,
            "aadhaar_seeding_status": self.aadhaar_seeding_status or "N/A",
            "cost_charged": str(self.cost_charged) if self.cost_charged is not None else "0.00",
            "reference_id": self.reference_id or "-",
            "server_ip": self.server_ip or "187.127.139.6",
            "ip_address": self.ip_address or "Unknown",
            "method": self.method or "CVL KRA",
            "endpoint": self.endpoint or "/services/pan",
            "user_agent": self.user_agent or "-",
            "duration_ms": self.duration_ms or 0,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if self.created_at else "-",
            "created_at_iso": self.created_at.isoformat() if self.created_at else None,
            "user": user_info,
            "company": company_info,
            "raw_request": self.raw_request or "",
            "raw_response": self.raw_response or "",
            "request_data": self.request_dict,
            "response_data": self.response_dict
        }

    def __repr__(self):
        return f"<PANVerification {self.pan_number} - {self.status}>"
