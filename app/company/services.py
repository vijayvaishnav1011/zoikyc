import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app
from app.extensions import db
from app.models.document import CompanyDocument
from app.models.company import Company

REQUIRED_DOCUMENTS = {
    'certificate_of_incorporation': 'Certificate of Incorporation / Registration',
    'company_pan': 'Company PAN Card Document',
    'gst_certificate': 'GSTIN Registration Certificate',
    'board_resolution': 'Authorised Signatory / Director KYC Proof (Board Resolution / POA / ID)'
}

def upload_company_document(company_id, document_type, file_storage, notes=None):
    """
    Saves uploaded file securely to uploads/documents/<company_id>/
    and records or updates the CompanyDocument entry in the database.
    """
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    unique_filename = f"{document_type}_{uuid.uuid4().hex[:8]}.{ext}"

    # Folder path
    upload_folder = os.path.join(current_app.root_path, 'uploads', 'documents', str(company_id))
    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, unique_filename)
    file_storage.save(file_path)

    # Relative path stored in DB
    relative_path = f"uploads/documents/{company_id}/{unique_filename}"

    # Find existing or create new
    doc = CompanyDocument.query.filter_by(company_id=company_id, document_type=document_type).first()
    if not doc:
        doc = CompanyDocument(
            company_id=company_id,
            document_type=document_type,
            document_name=filename,
            file_path=relative_path,
            status='under_review',
            notes=notes
        )
        db.session.add(doc)
    else:
        doc.document_name = filename
        doc.file_path = relative_path
        doc.status = 'under_review'
        doc.notes = notes

    db.session.commit()

    # Check submitted documents
    submitted_docs = CompanyDocument.query.filter_by(company_id=company_id).all()
    submitted_set = set(d.document_type for d in submitted_docs)
    approved_set = set(d.document_type for d in submitted_docs if d.status == 'approved')

    company = Company.query.get(company_id)
    if company:
        if set(REQUIRED_DOCUMENTS.keys()).issubset(approved_set):
            company.status = 'active'
        elif set(REQUIRED_DOCUMENTS.keys()).issubset(submitted_set):
            company.status = 'pending_verification'
        db.session.commit()

    return doc
