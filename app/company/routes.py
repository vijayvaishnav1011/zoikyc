import os
from flask import render_template, redirect, url_for, flash, request, send_file, current_app, abort
from flask_login import login_required, current_user
from app.company import company_bp
from app.company.forms import CompanyProfileForm, CompanyDocumentUploadForm
from app.company.services import upload_company_document, REQUIRED_DOCUMENTS
from app.models.document import CompanyDocument
from app.models.user import User
from app.extensions import db

@company_bp.route('/company/profile', methods=['GET', 'POST'])
@login_required
def profile():
    company = current_user.company
    if not company:
        flash("No organisation associated with this user.", "danger")
        return redirect(url_for('dashboard.index'))

    form = CompanyProfileForm(obj=company)
    if form.company_name.data is None:
        form.company_name.data = company.name

    if form.validate_on_submit():
        company.name = form.company_name.data.strip()
        company.authorised_signatory_name = form.authorised_signatory_name.data.strip()
        company.phone = form.phone.data.strip()
        company.gstin = form.gstin.data.strip().upper() if form.gstin.data else None
        company.country = form.country.data.strip()
        company.state = form.state.data.strip()
        company.city = form.city.data.strip()
        company.zip_code = form.zip_code.data.strip()
        company.address = form.address.data.strip()

        db.session.commit()
        flash("Organisation profile updated successfully!", "success")
        return redirect(url_for('company.profile'))

    team_users = User.query.filter_by(company_id=company.id).all()

    return render_template(
        'company/profile.html',
        form=form,
        company=company,
        team_users=team_users
    )

@company_bp.route('/company/documents', methods=['GET', 'POST'])
@login_required
def documents():
    company = current_user.company
    if not company:
        flash("No organisation associated with this user.", "danger")
        return redirect(url_for('dashboard.index'))

    form = CompanyDocumentUploadForm()

    if request.method == 'POST':
        doc_type = request.form.get('document_type')
        doc_file = request.files.get('document_file')

        if doc_type and doc_file and doc_file.filename:
            try:
                doc = upload_company_document(
                    company_id=company.id,
                    document_type=doc_type,
                    file_storage=doc_file
                )
                doc_title = REQUIRED_DOCUMENTS.get(doc_type, doc_type)
                flash(f"'{doc_title}' uploaded successfully! Status: Under Review.", "success")
                return redirect(url_for('company.documents'))
            except Exception as e:
                flash(f"Failed to upload document: {str(e)}", "danger")
        else:
            flash("Please select a valid document file (PDF, PNG, JPG, DOCX).", "danger")

    # Fetch uploaded documents
    uploaded_docs = CompanyDocument.query.filter_by(company_id=company.id).all()
    uploaded_dict = {d.document_type: d for d in uploaded_docs}

    return render_template(
        'company/documents.html',
        form=form,
        company=company,
        required_docs=REQUIRED_DOCUMENTS,
        uploaded_dict=uploaded_dict
    )

@company_bp.route('/company/documents/<int:doc_id>/download')
@login_required
def download_document(doc_id):
    doc = CompanyDocument.query.get_or_404(doc_id)
    
    # Ensure current user belongs to the document's company (or is super_admin)
    if doc.company_id != current_user.company_id and current_user.role != 'super_admin':
        abort(403)

    # Resolve file path across app.root_path and project root
    actual_path = None
    if os.path.isabs(doc.file_path) and os.path.exists(doc.file_path):
        actual_path = doc.file_path
    else:
        candidate1 = os.path.join(current_app.root_path, doc.file_path)
        if os.path.exists(candidate1):
            actual_path = candidate1
        else:
            candidate2 = os.path.abspath(os.path.join(current_app.root_path, '..', doc.file_path))
            if os.path.exists(candidate2):
                actual_path = candidate2

    if not actual_path or not os.path.exists(actual_path):
        flash(f"Requested document file '{doc.document_name}' not found on server.", "danger")
        return redirect(url_for('company.documents'))

    return send_file(actual_path, download_name=doc.document_name, as_attachment=False)
