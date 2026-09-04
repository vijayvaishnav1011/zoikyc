import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, send_file, current_app, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.esign import esign_bp
from app.esign.forms import ESignUploadForm
from app.models.esign import ESignDocument
from app.models.company import Company
from app.models.wallet import Wallet
from app.integrations.capricorn import CapricornESignProvider
from app.extensions import db, csrf

@esign_bp.route('/esign')
@login_required
def index():
    company = current_user.company
    if not company:
        flash("No organisation associated with this user.", "danger")
        return redirect(url_for('dashboard.index'))

    query = ESignDocument.query.filter_by(company_id=company.id)

    search_query = request.args.get('q', '').strip()
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                ESignDocument.title.ilike(search_pattern),
                ESignDocument.signatory_name.ilike(search_pattern),
                ESignDocument.signatory_mobile.ilike(search_pattern),
                ESignDocument.client_remarks.ilike(search_pattern)
            )
        )

    status_filter = request.args.get('status', 'all').strip()
    base_docs = ESignDocument.query.filter_by(company_id=company.id)
    counts = {
        'all': base_docs.count(),
        'pending_admin': base_docs.filter_by(status='pending_admin').count(),
        'sent_to_capricorn': base_docs.filter_by(status='sent_to_capricorn').count(),
        'signed': base_docs.filter_by(status='signed').count(),
        'rejected_by_admin': base_docs.filter_by(status='rejected_by_admin').count(),
    }

    if status_filter != 'all' and status_filter in counts:
        query = query.filter_by(status=status_filter)

    documents = query.order_by(ESignDocument.created_at.desc()).all()

    wallet = Wallet.query.filter_by(company_id=company.id).first()
    per_sign_fee = company.per_kyc_price or Decimal('20.00')
    has_sufficient_balance = wallet and wallet.balance >= per_sign_fee
    is_kyc_active = (company.status == 'active')

    return render_template(
        'esign/index.html',
        documents=documents,
        counts=counts,
        current_status=status_filter,
        company=company,
        wallet=wallet,
        per_sign_fee=per_sign_fee,
        has_sufficient_balance=has_sufficient_balance,
        is_kyc_active=is_kyc_active,
        search_query=search_query
    )


@esign_bp.route('/esign/upload', methods=['GET', 'POST'])
@login_required
def upload():
    company = current_user.company
    if not company:
        flash("No organisation associated with this user.", "danger")
        return redirect(url_for('dashboard.index'))

    wallet = Wallet.query.filter_by(company_id=company.id).first()
    per_sign_fee = company.per_kyc_price or Decimal('20.00')
    wallet_balance = wallet.balance if wallet else Decimal('0.00')
    is_kyc_active = (company.status == 'active')

    # Pre-flight check on KYC
    if not is_kyc_active:
        flash("Organisation KYC verification is pending approval. You may upload documents, but admin dispatch requires an active verified account.", "warning")

    # Pre-flight check on balance
    if wallet_balance < per_sign_fee:
        flash(f"Low wallet balance! Your current balance is ₹{wallet_balance:.2f}. Each E-Sign requires ₹{per_sign_fee:.2f}. Please recharge before dispatch.", "warning")

    form = ESignUploadForm()

    if form.validate_on_submit():
        file_storage = form.pdf_file.data
        orig_filename = secure_filename(file_storage.filename)
        ext = orig_filename.rsplit('.', 1)[-1].lower() if '.' in orig_filename else 'pdf'
        unique_name = f"esign_{uuid.uuid4().hex[:10]}.{ext}"

        # Store in uploads/esign/<company_id>/
        upload_folder = os.path.join(current_app.root_path, 'uploads', 'esign', str(company.id))
        os.makedirs(upload_folder, exist_ok=True)

        full_path = os.path.join(upload_folder, unique_name)
        file_storage.save(full_path)

        relative_path = f"uploads/esign/{company.id}/{unique_name}"

        esign_doc = ESignDocument(
            company_id=company.id,
            created_by_user_id=current_user.id,
            title=form.title.data.strip(),
            original_filename=orig_filename,
            file_path=relative_path,
            signatory_name=form.signatory_name.data.strip(),
            signatory_mobile=form.signatory_mobile.data.strip(),
            signatory_email=form.signatory_email.data.strip() if form.signatory_email.data else None,
            client_remarks=form.client_remarks.data.strip() if form.client_remarks.data else None,
            page_num=form.page_num.data or '1',
            coordinates=form.coordinates.data.strip() if form.coordinates.data else '200,250,400,500',
            status='pending_admin',
            cost_charged=per_sign_fee
        )

        db.session.add(esign_doc)
        db.session.commit()

        flash(
            f"Document '{esign_doc.title}' uploaded successfully. It is now queued for Super Admin review and Capricorn dispatch.",
            "success"
        )
        return redirect(url_for('esign.index'))

    return render_template(
        'esign/upload.html',
        form=form,
        company=company,
        wallet_balance=wallet_balance,
        per_sign_fee=per_sign_fee,
        is_kyc_active=is_kyc_active
    )

@esign_bp.route('/esign/<int:doc_id>/download')
@login_required
def download(doc_id):
    doc = ESignDocument.query.get_or_404(doc_id)

    # Permission check: must belong to company or be super admin
    if current_user.role != 'super_admin' and doc.company_id != current_user.company_id:
        abort(403)

    req_type = request.args.get('type', 'original')
    if req_type == 'signed' and doc.signed_file_path:
        full_path = os.path.join(current_app.root_path, doc.signed_file_path)
        download_name = f"Signed_{doc.original_filename}"
    else:
        full_path = os.path.join(current_app.root_path, doc.file_path)
        download_name = doc.original_filename

    if not os.path.exists(full_path):
        flash("Requested document file could not be found on server storage.", "danger")
        return redirect(url_for('esign.index'))

    return send_file(full_path, as_attachment=True, download_name=download_name)

@esign_bp.route('/esign/portal')
@login_required
def direct_portal():
    """Direct shortcut to open Capricorn Demo E-Sign portal."""
    return redirect("https://demo.esign.digital/esign/2.1/signdockyc/")

@esign_bp.route('/esign/<int:doc_id>/sign')
@login_required
def sign(doc_id):
    doc = ESignDocument.query.get_or_404(doc_id)

    if current_user.role != 'super_admin' and doc.company_id != current_user.company_id:
        abort(403)

    if doc.status == 'sent_to_capricorn' and doc.redirect_url:
        target_url = doc.redirect_url
        if "demo.esign.network" in target_url:
            try:
                head_resp = requests.get(target_url, allow_redirects=False, timeout=10)
                loc = head_resp.headers.get("Location") or head_resp.headers.get("location")
                if loc and "?param=" in loc:
                    target_url = f"https://demo.esign.digital/esign/2.1/signdockyc/?param={loc.split('?param=')[-1]}"
                    doc.redirect_url = target_url
                    db.session.commit()
                else:
                    target_url = "https://demo.esign.digital/esign/2.1/signdockyc/"
            except Exception:
                target_url = "https://demo.esign.digital/esign/2.1/signdockyc/"
        return redirect(target_url)
    elif doc.status == 'signed':
        flash("This document has already been digitally signed and sealed.", "info")
    else:
        # If pending or without active session, direct to the live portal
        return redirect("https://demo.esign.digital/esign/2.1/signdockyc/")

    return redirect(url_for('esign.index'))


@esign_bp.route('/esign/callback', methods=['GET', 'POST'])
@csrf.exempt
def callback():
    """
    Public Callback endpoint invoked by Capricorn upon signer OTP completion.
    Accepts GET redirect query params or POST webhook JSON payload.
    """
    txn = request.args.get('txn') or request.form.get('txn')
    reference = request.args.get('reference') or request.form.get('reference')
    signed_pdf_url = request.args.get('signedpdfurl') or request.form.get('signedpdfurl')
    status_param = request.args.get('status') or request.form.get('status')

    current_app.logger.info(f"Capricorn E-Sign callback received: txn={txn}, ref={reference}, status={status_param}")

    # Locate the document
    doc = None
    if reference:
        doc = ESignDocument.query.filter_by(capricorn_reference=reference).first()
    if not doc and txn:
        doc = ESignDocument.query.filter_by(capricorn_txn=txn).first()

    if not doc:
        current_app.logger.warning(f"Capricorn callback doc not found for txn={txn}, ref={reference}")
        if request.method == 'GET':
            flash("E-Sign session completed, but document record could not be matched.", "warning")
            return redirect(url_for('esign.index'))
        return jsonify({"status": "not_found", "message": "Document reference not found"}), 404

    # If already signed, nothing to do
    if doc.status == 'signed':
        if request.method == 'GET':
            flash("Document is already signed and archived.", "info")
            return redirect(url_for('esign.index'))
        return jsonify({"status": "success", "message": "Already signed"}), 200

    # Retrieve signed PDF URL if passed or fallback
    download_url = signed_pdf_url or doc.signed_pdf_url
    if download_url:
        capricorn = CapricornESignProvider()
        signed_name = f"signed_{os.path.basename(doc.file_path)}"
        target_dir = os.path.join(current_app.root_path, 'uploads', 'esign', str(doc.company_id))
        target_path = os.path.join(target_dir, signed_name)

        success = capricorn.download_signed_pdf(download_url, target_path)
        if success:
            doc.signed_file_path = f"uploads/esign/{doc.company_id}/{signed_name}"
            doc.status = 'signed'
            doc.signed_at = datetime.now(timezone.utc)
            db.session.commit()
            current_app.logger.info(f"Successfully downloaded signed PDF for doc {doc.id}")
        else:
            current_app.logger.error(f"Failed to fetch signed PDF from {download_url} for doc {doc.id}")
            doc.status = 'signed'  # Mark signed even if background download needs retry
            doc.signed_at = datetime.now(timezone.utc)
            db.session.commit()
    else:
        doc.status = 'signed'
        doc.signed_at = datetime.now(timezone.utc)
        db.session.commit()

    if request.method == 'GET':
        flash(f"Aadhaar OTP verification completed! Document '{doc.title}' has been digitally signed.", "success")
        return redirect(url_for('esign.index'))

    return jsonify({"status": "success", "doc_id": doc.id}), 200
