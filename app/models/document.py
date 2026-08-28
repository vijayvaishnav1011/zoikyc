from datetime import datetime, timezone
from app.extensions import db

class CompanyDocument(db.Model):
    __tablename__ = 'company_documents'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True)
    document_type = db.Column(db.String(50), nullable=False) 
    # certificate_of_incorporation, company_pan, gst_certificate, board_resolution, bank_proof
    
    document_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='under_review') # pending, under_review, approved, rejected
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<CompanyDocument {self.document_type} (Company ID: {self.company_id})>"
