import json
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.pan import pan_bp
from app.pan.forms import PANCheckForm
from app.models.pan import PANVerification
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.integrations.pan import PANVerificationProvider

@pan_bp.route('/services/pan', methods=['GET', 'POST'])
@login_required
def index():
    company = current_user.company
    if not company:
        flash("No organisation associated with this user.", "danger")
        return redirect(url_for('dashboard.index'))

    wallet = Wallet.query.filter_by(company_id=company.id).first()
    wallet_balance = wallet.balance if wallet else Decimal('0.00')

    form = PANCheckForm()
    result = None

    # Optional search / filter for recent checks
    search_query = request.args.get('q', '').strip().upper()
    status_filter = request.args.get('status', 'all').strip().lower()

    query = PANVerification.query.filter_by(company_id=company.id)

    if search_query:
        query = query.filter(
            (PANVerification.pan_number.ilike(f"%{search_query}%")) |
            (PANVerification.full_name.ilike(f"%{search_query}%"))
        )

    if status_filter in ['verified', 'failed', 'invalid']:
        query = query.filter_by(status=status_filter)

    recent_checks = query.order_by(PANVerification.created_at.desc()).limit(50).all()

    # Total counts for statistics
    total_checks = PANVerification.query.filter_by(company_id=company.id).count()
    verified_count = PANVerification.query.filter_by(company_id=company.id, status='verified').count()
    failed_count = PANVerification.query.filter_by(company_id=company.id, status='failed').count()

    if form.validate_on_submit():
        pan_number = form.pan_number.data.strip().upper()
        dob = form.dob.data.strip()

        # Free service - no wallet deduction
        charge_amount = Decimal('0.00')

        # Call PAN Verification Gateway
        provider = PANVerificationProvider()
        verification_data = provider.verify_pan_with_dob(
            pan_number=pan_number,
            dob=dob,
            company=company
        )

        # Save to database
        record = PANVerification(
            company_id=company.id,
            user_id=current_user.id,
            pan_number=pan_number,
            dob=dob,
            status=verification_data.get('status', 'failed'),
            status_message=verification_data.get('status_message'),
            full_name=verification_data.get('full_name'),
            first_name=verification_data.get('first_name'),
            middle_name=verification_data.get('middle_name'),
            last_name=verification_data.get('last_name'),
            category=verification_data.get('category'),
            pan_status=verification_data.get('pan_status'),
            dob_match=verification_data.get('dob_match'),
            aadhaar_seeding_status=verification_data.get('aadhaar_seeding_status'),
            cost_charged=charge_amount,
            reference_id=verification_data.get('reference_id'),
            raw_response=json.dumps(verification_data.get('raw_response', {}))
        )
        db.session.add(record)
        db.session.commit()

        result = {
            "record": record,
            "data": verification_data
        }

        if verification_data.get('status') == 'verified':
            flash(f"PAN {pan_number} verified successfully: {verification_data.get('full_name')}", "success")
        else:
            flash(f"PAN verification failed: {verification_data.get('status_message')}", "danger")

        # Refresh recent checks after submit
        recent_checks = query.order_by(PANVerification.created_at.desc()).limit(50).all()

    return render_template(
        'client/pan.html',
        form=form,
        result=result,
        recent_checks=recent_checks,
        company=company,
        wallet=wallet,
        wallet_balance=wallet_balance,
        total_checks=total_checks,
        verified_count=verified_count,
        failed_count=failed_count,
        search_query=search_query,
        status_filter=status_filter
    )
