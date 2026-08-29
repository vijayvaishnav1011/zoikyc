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

@admin_bp.route('/')
@admin_required
def index():
    # Platform Analytics Metrics
    total_companies = Company.query.count()
    active_companies = Company.query.filter_by(status='active').count()
    pending_companies = Company.query.filter_by(status='pending_verification').count()
    
    pending_documents = CompanyDocument.query.filter(
        CompanyDocument.status.in_(['under_review', 'pending'])
    ).count()

    total_wallet_reserves = db.session.query(
        func.coalesce(func.sum(Wallet.balance), 0)
    ).scalar()

    total_transactions = WalletTransaction.query.count()
    total_credit_volume = db.session.query(
        func.coalesce(func.sum(WalletTransaction.amount), 0)
    ).filter_by(type='credit', status='success').scalar()

    recent_companies = Company.query.order_by(Company.created_at.desc()).limit(6).all()
    pending_docs = CompanyDocument.query.filter(
        CompanyDocument.status.in_(['under_review', 'pending'])
    ).order_by(CompanyDocument.created_at.desc()).limit(6).all()
    
    recent_transactions = WalletTransaction.query.order_by(
        WalletTransaction.created_at.desc()
    ).limit(6).all()

    return render_template(
        'admin/index.html',
        total_companies=total_companies,
        active_companies=active_companies,
        pending_companies=pending_companies,
        pending_documents=pending_documents,
        total_wallet_reserves=total_wallet_reserves,
        total_transactions=total_transactions,
        total_credit_volume=total_credit_volume,
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

    query = Company.query

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
        search_query=search_query
    )

@admin_bp.route('/companies/<int:company_id>')
@admin_required
def company_detail(company_id):
    company = Company.query.get_or_404(company_id)
    users = company.users.order_by(User.created_at.asc()).all()
    documents = company.documents.order_by(CompanyDocument.created_at.desc()).all()
    transactions = company.transactions.order_by(WalletTransaction.created_at.desc()).limit(15).all()

    # Document completion mapping
    docs_by_type = {doc.document_type: doc for doc in documents}
    
    required_doc_types = [
        ('certificate_of_incorporation', 'Certificate of Incorporation'),
        ('company_pan', 'Company PAN Card'),
        ('gst_certificate', 'GSTIN Registration'),
        ('board_resolution', 'Authorised Signatory Proof'),
        ('bank_proof', 'Bank Account Proof')
    ]

    return render_template(
        'admin/company_detail.html',
        company=company,
        users=users,
        documents=documents,
        transactions=transactions,
        docs_by_type=docs_by_type,
        required_doc_types=required_doc_types
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

@admin_bp.route('/documents')
@admin_required
def documents():
    status_filter = request.args.get('status', 'all')
    doc_type_filter = request.args.get('doc_type', 'all')
    page = request.args.get('page', 1, type=int)

    query = CompanyDocument.query.join(Company)

    if status_filter != 'all':
        query = query.filter(CompanyDocument.status == status_filter)

    if doc_type_filter != 'all':
        query = query.filter(CompanyDocument.document_type == doc_type_filter)

    pagination = query.order_by(CompanyDocument.created_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template(
        'admin/documents.html',
        documents=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        doc_type_filter=doc_type_filter
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

        # Check if all 5 required docs are approved
        required_types = ['certificate_of_incorporation', 'company_pan', 'gst_certificate', 'board_resolution', 'bank_proof']
        approved_count = CompanyDocument.query.filter(
            CompanyDocument.company_id == doc.company_id,
            CompanyDocument.document_type.in_(required_types),
            CompanyDocument.status == 'approved'
        ).count()

        if approved_count >= 5:
            company = doc.company
            if company.status != 'active':
                company.status = 'active'
                company.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                flash(f"Document approved! All 5 compliance documents verified. Company '{company.name}' is now fully ACTIVE.", "success")
            else:
                flash("Document approved successfully.", "success")
        else:
            flash(f"Document approved. ({approved_count}/5 documents approved for this company).", "success")

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
