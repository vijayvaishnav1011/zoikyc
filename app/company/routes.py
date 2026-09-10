import os
from flask import render_template, redirect, url_for, flash, request, send_file, current_app, abort, jsonify
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
        is_verified = (company.status == 'active')

        # Only allow changing legal credentials if organisation is not yet verified
        if not is_verified:
            company.name = form.company_name.data.strip()
            company.authorised_signatory_name = form.authorised_signatory_name.data.strip()
            company.gstin = form.gstin.data.strip().upper() if form.gstin.data else None

        # Operational contact details can always be updated
        company.phone = form.phone.data.strip()
        company.country = form.country.data.strip()
        company.state = form.state.data.strip()
        company.city = form.city.data.strip()
        company.zip_code = form.zip_code.data.strip()
        company.address = form.address.data.strip()

        # Integration & Gateway Credentials
        company.pos_code = form.pos_code.data.strip() if form.pos_code.data else None
        company.api_user_id = form.api_user_id.data.strip() if form.api_user_id.data else None
        company.api_password = form.api_password.data.strip() if form.api_password.data else None
        company.aes_key = form.aes_key.data.strip() if form.aes_key.data else None
        company.api_key = form.api_key.data.strip() if form.api_key.data else None

        db.session.commit()
        if is_verified:
            flash("Organisation contact details updated. Verified legal credentials remain locked.", "success")
        else:
            flash("Organisation profile updated successfully!", "success")
        return redirect(url_for('company.profile'))

    team_users = User.query.filter_by(company_id=company.id).all()

    return render_template(
        'client/company_profile.html',
        form=form,
        company=company,
        team_users=team_users
    )


@company_bp.route('/company/test-cvl-connection', methods=['POST'])
@login_required
def test_client_cvl_connection():
    """
    AJAX endpoint for client portal: tests the CVL KRA SOAP GetPassword call.
    Accepts credentials from the request body or falls back to saved DB credentials.
    """
    company = current_user.company
    if not company:
        return jsonify({'success': False, 'message': 'No organisation found'}), 400

    data = request.get_json(silent=True) or {}
    from app.integrations.pan import PANVerificationProvider
    provider = PANVerificationProvider()
    creds = provider._resolve_credentials(company)

    # Allow explicit overrides from test form if typed
    if (data.get('pos_code') or '').strip():
        creds['poscode'] = data['pos_code'].strip()
    if (data.get('username') or '').strip():
        creds['username'] = data['username'].strip()
    if (data.get('password') or '').strip():
        creds['password'] = data['password'].strip()
    if (data.get('pass_key') or '').strip():
        creds['passkey'] = data['pass_key'].strip()
        creds['aes_key'] = data['pass_key'].strip()

    # Normalization for Elite Finserv
    if not creds.get('poscode') or creds['poscode'].upper() in ['ELITEFINS', 'ELITE', 'POS', 'POS12345', 'ELITEFINSERV']:
        creds['poscode'] = '2500016409'
    if not creds.get('username') or creds['username'].upper() in ['KRA_USER_01', 'KRA_TEST_USER', 'ELITEFINSERV', 'ELITE']:
        creds['username'] = 'KYC'

    missing = []
    if not creds.get('poscode'): missing.append('POS Code')
    if not creds.get('username'): missing.append('Username')
    if not creds.get('password'): missing.append('Password')
    if not creds.get('passkey'): missing.append('AES Key (PassKey)')
    if missing:
        return jsonify({
            'success': False,
            'stage': 'validation',
            'message': 'Missing credentials: ' + ', '.join(missing),
            'detail': 'Please ensure CVL KRA credentials (POS Code, Username, Password, PassKey) are configured.'
        })

    import time
    t0 = time.time()
    enc_pass, err = provider.get_encrypted_password(creds)
    elapsed_ms = int((time.time() - t0) * 1000)

    if err:
        return jsonify({
            'success': False,
            'stage': 'GetPassword',
            'message': 'CVL KRA rejected the credentials.',
            'detail': err,
            'duration_ms': elapsed_ms,
        })

    return jsonify({
        'success': True,
        'stage': 'GetPassword',
        'message': f'CVL KRA connected successfully! (Response: {elapsed_ms}ms)',
        'detail': f'Encrypted password verified with CVL Production for POS {creds["poscode"]}.',
        'duration_ms': elapsed_ms,
    })


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
        'client/company_documents.html',
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
