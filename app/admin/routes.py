import os
from decimal import Decimal
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, send_file, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from app.admin import admin_bp
from app.admin.decorators import admin_required
from app.extensions import db
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.models.document import CompanyDocument
from app.models.setting import SystemSetting, get_platform_fee_config
from app.models.esign import ESignDocument
from app.integrations.capricorn import CapricornESignProvider

REQUIRED_KYC_DOCS = [
    ('certificate_of_incorporation', 'Certificate of Incorporation'),
    ('company_pan', 'Company PAN Card'),
    ('gst_certificate', 'GSTIN Registration'),
    ('board_resolution', 'Authorised Signatory / Director Proof')
]

ADMIN_SYSTEM_EMAILS = ['info@zoibit.com', 'admin@zoikyc.com', 'info@zoikyc.com']

@admin_bp.route('/')
@admin_required
def index():
    # Platform Analytics Metrics (Excluding internal admin tenant)
    client_companies = Company.query.filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS))
    
    total_companies = client_companies.count()
    active_companies = client_companies.filter_by(status='active').count()
    pending_companies = client_companies.filter_by(status='pending_verification').count()
    
    pending_documents = CompanyDocument.query.join(Company).filter(
        Company.email.notin_(ADMIN_SYSTEM_EMAILS),
        CompanyDocument.status.in_(['under_review', 'pending'])
    ).count()

    total_wallet_reserves = db.session.query(
        func.coalesce(func.sum(Wallet.balance), 0)
    ).join(Company).filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS)).scalar()

    total_transactions = WalletTransaction.query.join(Company).filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS)).count()
    total_credit_volume = db.session.query(
        func.coalesce(func.sum(WalletTransaction.amount), 0)
    ).join(Company).filter(
        Company.email.notin_(ADMIN_SYSTEM_EMAILS),
        WalletTransaction.type == 'credit',
        WalletTransaction.status == 'success'
    ).scalar()

    recent_companies = client_companies.order_by(Company.created_at.desc()).limit(6).all()
    pending_docs = CompanyDocument.query.join(Company).filter(
        Company.email.notin_(ADMIN_SYSTEM_EMAILS),
        CompanyDocument.status.in_(['under_review', 'pending'])
    ).order_by(CompanyDocument.created_at.desc()).limit(6).all()
    
    recent_transactions = WalletTransaction.query.join(Company).filter(
        Company.email.notin_(ADMIN_SYSTEM_EMAILS)
    ).order_by(
        WalletTransaction.created_at.desc()
    ).limit(6).all()

    fee_percent, fee_name = get_platform_fee_config()

    return render_template(
        'admin/index.html',
        total_companies=total_companies,
        active_companies=active_companies,
        pending_companies=pending_companies,
        pending_documents=pending_documents,
        total_wallet_reserves=total_wallet_reserves,
        total_transactions=total_transactions,
        total_credit_volume=total_credit_volume,
        fee_percent=fee_percent,
        fee_name=fee_name,
        recent_companies=recent_companies,
        pending_docs=pending_docs,
        recent_transactions=recent_transactions
    )

@admin_bp.route('/companies')
@admin_required
def companies():
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    # Base query excluding internal admin
    base_query = Company.query.filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS))
    total_count = base_query.count()
    active_count = base_query.filter_by(status='active').count()
    pending_count = base_query.filter_by(status='pending_verification').count()
    suspended_count = base_query.filter_by(status='suspended').count()

    query = base_query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            (Company.name.ilike(search)) |
            (Company.email.ilike(search)) |
            (Company.authorised_signatory_name.ilike(search)) |
            (Company.gstin.ilike(search))
        )

    pagination = query.order_by(Company.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    
    return render_template(
        'admin/companies.html',
        companies=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        search_query=search_query,
        total_count=total_count,
        active_count=active_count,
        pending_count=pending_count,
        suspended_count=suspended_count
    )

@admin_bp.route('/companies/<int:company_id>')
@admin_bp.route('/company/<int:company_id>')
@admin_required
def company_detail(company_id):
    company = Company.query.get_or_404(company_id)
    users = company.users.order_by(User.created_at.asc()).all()
    documents = company.documents.order_by(CompanyDocument.created_at.desc()).all()
    transactions = company.transactions.order_by(WalletTransaction.created_at.desc()).limit(15).all()

    # Document completion mapping
    docs_by_type = {doc.document_type: doc for doc in documents}

    return render_template(
        'admin/company_detail.html',
        company=company,
        users=users,
        documents=documents,
        transactions=transactions,
        docs_by_type=docs_by_type,
        required_doc_types=REQUIRED_KYC_DOCS
    )

@admin_bp.route('/companies/<int:company_id>/status', methods=['POST'])
@admin_required
def update_company_status(company_id):
    company = Company.query.get_or_404(company_id)
    new_status = request.form.get('status')
    
    if new_status in ['active', 'pending_verification', 'suspended']:
        company.status = new_status
        company.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Company status for '{company.name}' updated to {new_status.replace('_', ' ').title()}.", "success")
    else:
        flash("Invalid status specified.", "danger")

    return redirect(request.referrer or url_for('admin.company_detail', company_id=company.id))

@admin_bp.route('/companies/<int:company_id>/approve-all', methods=['POST'])
@admin_required
def approve_all_documents(company_id):
    company = Company.query.get_or_404(company_id)
    notes = request.form.get('notes', 'Bulk approved by Administrator')

    docs = company.documents.all()
    for doc in docs:
        doc.status = 'approved'
        doc.notes = notes
        doc.updated_at = datetime.now(timezone.utc)

    # Check if all 4 required types exist and are approved
    required_keys = [t[0] for t in REQUIRED_KYC_DOCS]
    existing_types = set(d.document_type for d in docs)
    
    if set(required_keys).issubset(existing_types):
        company.status = 'active'
        company.updated_at = datetime.now(timezone.utc)
        flash(f"All 4 documents approved! Company '{company.name}' is now fully ACTIVE and verified.", "success")
    else:
        flash(f"Approved all existing documents for '{company.name}'. (Some mandatory docs still missing).", "info")

    db.session.commit()
    return redirect(request.referrer or url_for('admin.company_detail', company_id=company.id))

@admin_bp.route('/documents')
@admin_required
def documents():
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    # Exclude internal admin tenant from document verification matrix
    query = Company.query.filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS))

    if status_filter == 'pending':
        query = query.filter(Company.status != 'active')
    elif status_filter == 'active':
        query = query.filter_by(status='active')
    elif status_filter == 'suspended':
        query = query.filter_by(status='suspended')

    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            (Company.name.ilike(search)) |
            (Company.email.ilike(search)) |
            (Company.authorised_signatory_name.ilike(search)) |
            (Company.gstin.ilike(search))
        )

    pagination = query.order_by(Company.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

    required_keys = [t[0] for t in REQUIRED_KYC_DOCS]

    # Pre-map document status per company
    companies_data = []
    for comp in pagination.items:
        comp_docs = comp.documents.all()
        doc_dict = {d.document_type: d for d in comp_docs}
        approved_count = sum(1 for d in comp_docs if d.status == 'approved' and d.document_type in required_keys)
        under_review_count = sum(1 for d in comp_docs if d.status == 'under_review' and d.document_type in required_keys)
        
        companies_data.append({
            'company': comp,
            'docs': doc_dict,
            'uploaded_count': len(comp_docs),
            'approved_count': approved_count,
            'under_review_count': under_review_count
        })

    return render_template(
        'admin/documents.html',
        companies_data=companies_data,
        pagination=pagination,
        status_filter=status_filter,
        search_query=search_query,
        required_doc_types=REQUIRED_KYC_DOCS
    )

@admin_bp.route('/documents/<int:doc_id>/action', methods=['POST'])
@admin_required
def document_action(doc_id):
    doc = CompanyDocument.query.get_or_404(doc_id)
    action = request.form.get('action') # approve, reject
    notes = request.form.get('notes', '').strip()

    if action == 'approve':
        doc.status = 'approved'
        doc.notes = notes or 'Approved by Administrator'
        doc.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Check if all 4 required docs are approved
        required_types = ['certificate_of_incorporation', 'company_pan', 'gst_certificate', 'board_resolution']
        approved_count = CompanyDocument.query.filter(
            CompanyDocument.company_id == doc.company_id,
            CompanyDocument.document_type.in_(required_types),
            CompanyDocument.status == 'approved'
        ).count()

        if approved_count >= 4:
            company = doc.company
            if company.status != 'active':
                company.status = 'active'
                company.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                flash(f"Document approved! All 4 compliance documents verified. Company '{company.name}' is now fully ACTIVE.", "success")
            else:
                flash("Document approved successfully.", "success")
        else:
            flash(f"Document approved. ({approved_count}/4 documents approved for this company).", "success")

    elif action == 'reject':
        doc.status = 'rejected'
        doc.notes = notes or 'Rejected by Administrator. Please re-upload a clear document.'
        doc.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Document rejected with notice to client.", "warning")

    return redirect(request.referrer or url_for('admin.documents'))

@admin_bp.route('/documents/<int:doc_id>/download')
@admin_required
def download_document(doc_id):
    doc = CompanyDocument.query.get_or_404(doc_id)
    
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
        return redirect(request.referrer or url_for('admin.documents'))

    return send_file(actual_path, download_name=doc.document_name, as_attachment=False)

@admin_bp.route('/transactions')
@admin_required
def transactions():
    txn_type = request.args.get('type', 'all')
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = WalletTransaction.query.join(Company)

    if txn_type != 'all':
        query = query.filter(WalletTransaction.type == txn_type)

    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            (WalletTransaction.reference_id.ilike(search)) |
            (WalletTransaction.description.ilike(search)) |
            (Company.name.ilike(search))
        )

    pagination = query.order_by(WalletTransaction.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'admin/transactions.html',
        transactions=pagination.items,
        pagination=pagination,
        txn_type=txn_type,
        search_query=search_query
    )

@admin_bp.route('/companies/<int:company_id>/adjust-wallet', methods=['POST'])
@admin_required
def adjust_wallet(company_id):
    company = Company.query.get_or_404(company_id)
    amount_str = request.form.get('amount')
    action_type = request.form.get('action_type') # credit, debit
    reason = request.form.get('reason', '').strip() or 'Admin Manual Wallet Adjustment'

    try:
        amount = Decimal(str(amount_str))
        if amount <= 0:
            flash("Amount must be greater than zero.", "danger")
            return redirect(url_for('admin.company_detail', company_id=company.id))

        wallet = company.wallet
        if not wallet:
            wallet = Wallet(company_id=company.id, balance=Decimal('0.00'))
            db.session.add(wallet)
            db.session.commit()

        if action_type == 'debit' and wallet.balance < amount:
            flash(f"Insufficient funds: Company wallet balance is {wallet.balance}, cannot debit {amount}.", "danger")
            return redirect(url_for('admin.company_detail', company_id=company.id))

        balance_before = wallet.balance
        if action_type == 'credit':
            wallet.balance += amount
        else:
            wallet.balance -= amount

        wallet.updated_at = datetime.now(timezone.utc)
        
        # Log Transaction
        import uuid
        ref_id = f"ADM_{uuid.uuid4().hex[:10].upper()}"
        txn = WalletTransaction(
            wallet_id=wallet.id,
            company_id=company.id,
            type=action_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference_id=ref_id,
            description=f"[Admin Adjustment: {current_user.name}] {reason}",
            status='success'
        )
        db.session.add(txn)
        db.session.commit()

        flash(f"Wallet successfully {action_type}ed by ₹{amount:,.2f}. New Balance: ₹{wallet.balance:,.2f} (Ref: {ref_id})", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error adjusting wallet: {str(e)}", "danger")

    return redirect(url_for('admin.company_detail', company_id=company.id))

@admin_bp.route('/companies/<int:company_id>/send-low-balance-alert', methods=['POST'])
@admin_required
def send_low_balance_alert(company_id):
    from app.wallet.services import send_low_balance_alert_email
    company = Company.query.get_or_404(company_id)
    wallet = company.wallet
    balance = wallet.balance if wallet else Decimal('0.00')

    # Send low balance alert to company primary email and admin signatory
    primary_user = company.users.filter_by(role='company_admin').first()
    recipient_email = company.email
    recipient_name = company.authorised_signatory_name

    try:
        send_low_balance_alert_email(
            to_email=recipient_email,
            user_name=recipient_name,
            company_name=company.name,
            client_id=company.client_id,
            balance=balance
        )
        if primary_user and primary_user.email.lower() != recipient_email.lower():
            send_low_balance_alert_email(
                to_email=primary_user.email,
                user_name=primary_user.name,
                company_name=company.name,
                client_id=company.client_id,
                balance=balance
            )

        flash(f"Low balance alert email sent to '{company.name}' ({recipient_email}) with current balance ₹{balance:,.2f}.", "success")
    except Exception as e:
        flash(f"Failed to dispatch alert email: {str(e)}", "danger")

    return redirect(request.referrer or url_for('admin.company_detail', company_id=company.id))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        fee_percent_val = request.form.get('platform_fee_percent', '').strip()
        fee_name_val = request.form.get('platform_fee_name', '').strip()

        try:
            fee_percent_float = float(fee_percent_val)
            if fee_percent_float < 0 or fee_percent_float > 100:
                raise ValueError()
        except (ValueError, TypeError):
            flash('Please enter a valid percentage rate between 0 and 100.', 'danger')
            return redirect(url_for('admin.settings'))

        if not fee_name_val:
            fee_name_val = 'Platform Processing Fee'

        SystemSetting.set_val('platform_fee_percent', f"{fee_percent_float:.2f}", 'Platform fee percentage applied to recharges')
        SystemSetting.set_val('platform_fee_name', fee_name_val, 'Custom display name for platform fee')

        flash(f'Platform fee configuration updated successfully! Fee: {fee_percent_float:.2f}%, Label: "{fee_name_val}"', 'success')
        return redirect(url_for('admin.settings'))

    fee_percent, fee_name = get_platform_fee_config()
    return render_template('admin/settings.html', fee_percent=fee_percent, fee_name=fee_name)

@admin_bp.route('/company/<int:company_id>/pricing', methods=['POST'])
@admin_bp.route('/companies/<int:company_id>/pricing', methods=['POST'])
@admin_required
def update_company_pricing(company_id):
    company = Company.query.get_or_404(company_id)
    per_kyc_val = request.form.get('per_kyc_price', '').strip()
    min_rech_val = request.form.get('min_recharge_amount', '').strip()

    try:
        per_kyc = Decimal(per_kyc_val)
        if per_kyc < Decimal('0.00'):
            raise ValueError()
    except Exception:
        flash('Please enter a valid non-negative per-KYC verification price.', 'danger')
        return redirect(url_for('admin.company_detail', company_id=company.id))

    try:
        min_rech = Decimal(min_rech_val)
        if min_rech < Decimal('1.00'):
            raise ValueError()
    except Exception:
        flash('Please enter a valid minimum recharge amount (at least ₹1.00).', 'danger')
        return redirect(url_for('admin.company_detail', company_id=company.id))

    company.per_kyc_price = per_kyc
    company.min_recharge_amount = min_rech
    db.session.commit()

    flash(f"Updated commercial rules for '{company.name}' — Per KYC: ₹{per_kyc:,.2f} | Min Recharge: ₹{min_rech:,.2f}.", "success")
    return redirect(url_for('admin.company_detail', company_id=company.id))

# =========================================================================
# E-SIGN CAPRICORN DISPATCH & MANAGEMENT
# =========================================================================

@admin_bp.route('/esign')
@admin_required
def esign_requests():
    """Super Admin screen to review uploaded client documents and dispatch to Capricorn."""
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('q', '').strip()

    query = ESignDocument.query.join(Company).filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS))

    if status_filter != 'all':
        query = query.filter(ESignDocument.status == status_filter)

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                ESignDocument.title.ilike(search_pattern),
                ESignDocument.signatory_name.ilike(search_pattern),
                ESignDocument.signatory_mobile.ilike(search_pattern),
                ESignDocument.client_remarks.ilike(search_pattern),
                Company.name.ilike(search_pattern),
                Company.client_id.ilike(search_pattern)
            )
        )

    documents = query.order_by(ESignDocument.created_at.desc()).all()

    counts = {
        'all': ESignDocument.query.join(Company).filter(Company.email.notin_(ADMIN_SYSTEM_EMAILS)).count(),
        'pending_admin': ESignDocument.query.join(Company).filter(
            Company.email.notin_(ADMIN_SYSTEM_EMAILS),
            ESignDocument.status == 'pending_admin'
        ).count(),
        'sent_to_capricorn': ESignDocument.query.join(Company).filter(
            Company.email.notin_(ADMIN_SYSTEM_EMAILS),
            ESignDocument.status == 'sent_to_capricorn'
        ).count(),
        'signed': ESignDocument.query.join(Company).filter(
            Company.email.notin_(ADMIN_SYSTEM_EMAILS),
            ESignDocument.status == 'signed'
        ).count(),
        'rejected_by_admin': ESignDocument.query.join(Company).filter(
            Company.email.notin_(ADMIN_SYSTEM_EMAILS),
            ESignDocument.status == 'rejected_by_admin'
        ).count(),
    }

    return render_template(
        'admin/esign_requests.html',
        documents=documents,
        counts=counts,
        current_status=status_filter,
        search_query=search_query
    )

@admin_bp.route('/esign/<int:doc_id>/dispatch', methods=['POST'])
@admin_required
def dispatch_esign(doc_id):
    """
    Encodes the client PDF into Base64 (pdf64) and dispatches it to Capricorn API.
    Debits the per-sign fee from the client company's wallet and updates status to 'sent_to_capricorn'.
    """
    import uuid
    doc = ESignDocument.query.get_or_404(doc_id)
    company = doc.company
    wallet = Wallet.query.filter_by(company_id=company.id).first()

    per_sign_fee = company.per_kyc_price or Decimal('20.00')

    # Float balance verification
    if not wallet or wallet.balance < per_sign_fee:
        flash(
            f"Cannot dispatch document! Client '{company.name}' has insufficient wallet float "
            f"(Balance: ₹{wallet.balance if wallet else 0:.2f}, Required: ₹{per_sign_fee:.2f}). "
            f"Please notify client to recharge.",
            "danger"
        )
        return redirect(url_for('admin.esign_requests'))

    # Full server path to the original PDF
    pdf_full_path = os.path.join(current_app.root_path, doc.file_path)
    if not os.path.exists(pdf_full_path):
        flash(f"Original PDF file not found at path: {doc.file_path}", "danger")
        return redirect(url_for('admin.esign_requests'))

    # Build callback URL
    callback_url = url_for('esign.callback', _external=True)

    # Optional override coordinates from admin form
    custom_cood = request.form.get('coordinates', '').strip() or doc.coordinates or "200,250,400,500"
    custom_page = request.form.get('page_num', '').strip() or doc.page_num or "1"

    capricorn = CapricornESignProvider()
    result = capricorn.send_document_for_esign(
        doc_title=doc.title,
        pdf_file_path=pdf_full_path,
        signatory_name=doc.signatory_name,
        signatory_mobile=doc.signatory_mobile,
        signatory_email=doc.signatory_email,
        callback_url=callback_url,
        page_num=custom_page,
        coordinates=custom_cood,
        sign_mode=doc.sign_mode
    )

    if not result.get('success'):
        error_msg = result.get('error', 'Unknown error from Capricorn')
        flash(f"Capricorn API dispatch failed: {error_msg}", "danger")
        return redirect(url_for('admin.esign_requests'))

    # API call succeeded! Deduct fee from client's wallet
    balance_before = wallet.balance
    wallet.balance -= per_sign_fee
    balance_after = wallet.balance

    txn_ref = f"ESIGN-{doc.id}-{uuid.uuid4().hex[:6].upper()}"
    wallet_txn = WalletTransaction(
        wallet_id=wallet.id,
        company_id=company.id,
        type='debit',
        amount=per_sign_fee,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_id=txn_ref,
        status='success',
        description=f"Aadhaar E-Sign charge for '{doc.title}' (Txn: {result.get('txn')})"
    )
    db.session.add(wallet_txn)

    # Update document state
    doc.status = 'sent_to_capricorn'
    doc.capricorn_txn = result.get('txn')
    doc.capricorn_reference = result.get('reference')
    doc.redirect_url = result.get('redirect_url')
    doc.signed_pdf_url = result.get('signed_pdf_url')
    doc.cost_charged = per_sign_fee
    doc.coordinates = custom_cood
    doc.page_num = custom_page
    doc.dispatched_at = datetime.now(timezone.utc)
    doc.admin_notes = None

    db.session.commit()

    flash(
        f"Document '{doc.title}' successfully converted to Base64 and dispatched to Capricorn! "
        f"Txn: {doc.capricorn_txn}. Debited ₹{per_sign_fee:.2f} from {company.name}.",
        "success"
    )
    return redirect(url_for('admin.esign_requests'))

@admin_bp.route('/esign/<int:doc_id>/reject', methods=['POST'])
@admin_required
def reject_esign(doc_id):
    """Rejects an e-sign document request with admin feedback."""
    doc = ESignDocument.query.get_or_404(doc_id)
    reason = request.form.get('admin_notes', 'Document rejected by compliance administrator.').strip()

    doc.status = 'rejected_by_admin'
    doc.admin_notes = reason
    db.session.commit()

    flash(f"Document '{doc.title}' rejected.", "info")
    return redirect(url_for('admin.esign_requests'))

@admin_bp.route('/esign/<int:doc_id>/preview')
@admin_required
def preview_esign(doc_id):
    """Allows Super Admin to inspect original or signed PDF."""
    doc = ESignDocument.query.get_or_404(doc_id)
    req_type = request.args.get('type', 'original')

    if req_type == 'signed' and doc.signed_file_path:
        full_path = os.path.join(current_app.root_path, doc.signed_file_path)
        download_name = f"Signed_{doc.original_filename}"
    else:
        full_path = os.path.join(current_app.root_path, doc.file_path)
        download_name = doc.original_filename

    if not os.path.exists(full_path):
        flash("Document file not found on storage.", "danger")
        return redirect(url_for('admin.esign_requests'))

    return send_file(full_path, as_attachment=False, download_name=download_name)




