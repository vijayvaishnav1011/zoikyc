import os
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db

class ESignDocument(db.Model):
    __tablename__ = 'esign_documents'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Document details
    title = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    signed_file_path = db.Column(db.String(500), nullable=True)

    # Signatory details
    signatory_name = db.Column(db.String(150), nullable=False)
    signatory_email = db.Column(db.String(150), nullable=True)
    signatory_mobile = db.Column(db.String(20), nullable=True, default='9999999999')
    sign_mode = db.Column(db.String(50), nullable=False, default='online-aadhaar-otp') # online-aadhaar-otp, dsc

    # Status tracking
    # pending_admin: Uploaded by client, awaiting admin review
    # rejected_by_admin: Admin rejected document
    # sent_to_capricorn: Dispatched by admin to Capricorn API, waiting for signer OTP
    # signed: Completed and verified with signed PDF saved
    # failed: API or signing error
    status = db.Column(db.String(50), nullable=False, default='pending_admin', index=True)
    admin_notes = db.Column(db.Text, nullable=True)
    client_remarks = db.Column(db.Text, nullable=True)

    # Capricorn API identifiers
    capricorn_txn = db.Column(db.String(100), nullable=True, index=True)
    capricorn_reference = db.Column(db.String(100), nullable=True, index=True)
    redirect_url = db.Column(db.Text, nullable=True)
    signed_pdf_url = db.Column(db.Text, nullable=True)

    # Signing configuration
    page_num = db.Column(db.String(20), nullable=False, default='1')
    coordinates = db.Column(db.String(100), nullable=False, default='200,250,400,500')

    # Financial tracking
    cost_charged = db.Column(db.Numeric(10, 2), nullable=True, default=Decimal('0.00'))

    # Raw Payload, Network & Audit Logs
    raw_request = db.Column(db.Text, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    server_ip = db.Column(db.String(100), nullable=True, default='187.127.139.6', index=True)
    ip_address = db.Column(db.String(100), nullable=True, index=True)
    method = db.Column(db.String(100), nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    signed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    company = db.relationship('Company', backref=db.backref('esign_documents', lazy='dynamic', cascade='all, delete-orphan'))
    created_by = db.relationship('User', backref=db.backref('created_esign_documents', lazy='dynamic'))

    def __repr__(self):
        return f"<ESignDocument {self.id}: {self.title} ({self.status})>"

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

    @property
    def status_badge_class(self):
        badges = {
            'pending_admin': 'badge-warning',
            'rejected_by_admin': 'badge-danger',
            'sent_to_capricorn': 'badge-info',
            'signed': 'badge-success',
            'failed': 'badge-danger'
        }
        return badges.get(self.status, 'badge-secondary')

    @property
    def status_label(self):
        labels = {
            'pending_admin': 'Pending Dispatch',
            'rejected_by_admin': 'Rejected',
            'sent_to_capricorn': 'Awaiting Aadhaar OTP',
            'signed': 'Signed & Verified',
            'failed': 'Signing Failed'
        }
        return labels.get(self.status, self.status.replace('_', ' ').title())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "status_label": self.status_label,
            "signatory_name": self.signatory_name,
            "signatory_mobile": self.signatory_mobile,
            "signatory_email": self.signatory_email,
            "capricorn_txn": self.capricorn_txn,
            "capricorn_reference": self.capricorn_reference,
            "sign_url": self.redirect_url,
            "signed_url": self.signed_pdf_url or (f"https://demo.esign.network/apij/getdoc/v1.0/{self.capricorn_txn}/{self.capricorn_reference}" if self.capricorn_txn and self.capricorn_reference else None),
            "signed_pdf_url": self.signed_pdf_url or (f"https://demo.esign.network/apij/getdoc/v1.0/{self.capricorn_txn}/{self.capricorn_reference}" if self.capricorn_txn and self.capricorn_reference else None),
            "cost_charged": float(self.cost_charged or Decimal('0.00')),
            "ip_address": self.ip_address,
            "server_ip": self.server_ip or '187.127.139.6',
            "method": self.method,
            "endpoint": self.endpoint,
            "user_agent": self.user_agent,
            "duration_ms": self.duration_ms,
            "raw_request": self.request_dict,
            "raw_response": self.response_dict,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "company": {
                "id": self.company.id if self.company else None,
                "name": self.company.name if self.company else None,
                "client_id": self.company.client_id if self.company else None,
            }
        }
