import json
import time
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.pan import pan_bp
from app.pan.forms import PANCheckForm
from app.models.pan import PANVerification
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.models.company import Company
from app.integrations.pan import PANVerificationProvider

def _extract_client_ip():
    """Extracts client IP prioritizing reverse proxies / Cloudflare headers."""
    if request.headers.get('CF-Connecting-IP'):
        return request.headers.get('CF-Connecting-IP').strip()
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP').strip()
    return request.remote_addr or '127.0.0.1'

@pan_bp.route('/services/pan', methods=['GET', 'POST'])
@login_required
def index():
    company = current_user.company
    if not company:
        if request.is_json or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": "No organisation associated with this user"}), 400
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

    def _fetch_stats_and_checks():
        return (
            query.order_by(PANVerification.created_at.desc()).limit(50).all(),
            PANVerification.query.filter_by(company_id=company.id).count(),
            PANVerification.query.filter_by(company_id=company.id, status='verified').count(),
            PANVerification.query.filter_by(company_id=company.id, status='failed').count()
        )

    try:
        recent_checks, total_checks, verified_count, failed_count = _fetch_stats_and_checks()
    except Exception as q_err:
        db.session.rollback()
        # Self-heal schema on the fly if columns are missing
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS raw_request TEXT;"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS raw_response TEXT;"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS dob VARCHAR(20);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS reference_id VARCHAR(100);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS aadhaar_seeding_status VARCHAR(100);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS pan_status VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS dob_match BOOLEAN;"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS ip_address VARCHAR(100);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS method VARCHAR(100);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS endpoint VARCHAR(255);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255);"))
            db.session.execute(text("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS duration_ms INTEGER;"))
            db.session.commit()
            recent_checks, total_checks, verified_count, failed_count = _fetch_stats_and_checks()
        except Exception:
            db.session.rollback()
            recent_checks = []
            total_checks = 0
            verified_count = 0
            failed_count = 0

    # Check if request is JSON API call
    is_json_req = request.is_json or request.args.get('format') == 'json' or request.headers.get('Accept') == 'application/json'

    # Support both JSON payload and standard Form submission
    pan_number = None
    dob = ""

    if request.is_json:
        req_json = request.get_json() or {}
        pan_number = (req_json.get('pan') or req_json.get('pan_number') or '').strip().upper()
        dob_day = str(req_json.get('dob_day') or req_json.get('day') or '').strip()
        dob_month = str(req_json.get('dob_month') or req_json.get('month') or '').strip()
        dob_year = str(req_json.get('dob_year') or req_json.get('year') or '').strip()
        if dob_day and dob_month and dob_year:
            dob = f"{dob_day.zfill(2)}/{dob_month.zfill(2)}/{dob_year}"
        else:
            dob = (req_json.get('dob') or '').strip()
        should_process = bool(pan_number)
    else:
        should_process = form.validate_on_submit()
        if should_process:
            pan_number = form.pan_number.data.strip().upper()
            dob_day = (request.form.get('dob_day') or form.dob_day.data or '').strip()
            dob_month = (request.form.get('dob_month') or form.dob_month.data or '').strip()
            dob_year = (request.form.get('dob_year') or form.dob_year.data or '').strip()
            if dob_day and dob_month and dob_year:
                dob = f"{dob_day.zfill(2)}/{dob_month.zfill(2)}/{dob_year}"
            else:
                dob = (form.dob.data or "").strip()

    if should_process and pan_number:
        if not dob:
            if is_json_req:
                return jsonify({
                    "success": False,
                    "status": "invalid",
                    "error": "Missing required field: 'dob'. Date of Birth is required."
                }), 400
            flash("Date of Birth is required. Please select Day, Month, and Year.", "danger")
            should_process = False

    if should_process and pan_number:
        # Free service - no wallet deduction
        charge_amount = Decimal('0.00')
        client_ip = _extract_client_ip()
        user_agent_str = (request.headers.get('User-Agent') or '')[:250]
        start_time = time.time()

        # Call PAN Verification Gateway (GetPANStatus)
        try:
            provider = PANVerificationProvider()
            verification_data = provider.verify_pan_with_dob(
                pan_number=pan_number,
                dob=dob,
                company=company
            )
        except Exception as prov_err:
            import logging
            logging.error(f"Error calling PAN verification provider: {prov_err}", exc_info=True)
            verification_data = {
                "success": False,
                "status": "failed",
                "status_message": f"Verification gateway error: {prov_err}",
                "method": "CVL Gateway Error",
                "raw_response": {"error": str(prov_err)}
            }
        duration_ms = int((time.time() - start_time) * 1000)

        # Save to database
        record = None
        try:
            raw_resp_str = verification_data.get('raw_response')
            if not isinstance(raw_resp_str, str):
                raw_resp_str = json.dumps(raw_resp_str or {})

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
                raw_response=raw_resp_str,
                raw_request=verification_data.get('raw_request'),
                ip_address=client_ip,
                method=verification_data.get('method', 'CVL KRA'),
                endpoint=request.path,
                user_agent=user_agent_str,
                duration_ms=duration_ms
            )
            db.session.add(record)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            import logging
            logging.error(f"Failed to save PAN Verification to database: {e}")

        # If requested as JSON, return instant JSON response
        if is_json_req and request.method == 'POST':
            return jsonify({
                "success": verification_data.get('success', False),
                "pan_number": pan_number,
                "status": verification_data.get('status'),
                "status_message": verification_data.get('status_message'),
                "full_name": verification_data.get('full_name'),
                "category": verification_data.get('category'),
                "pan_status": verification_data.get('pan_status'),
                "aadhaar_seeding_status": verification_data.get('aadhaar_seeding_status'),
                "reference_id": verification_data.get('reference_id'),
                "method": verification_data.get('method', 'GetPANStatus'),
                "raw_response": verification_data.get('raw_response'),
                "ip_address": client_ip,
                "duration_ms": duration_ms
            })

        result = {
            "record": record,
            "data": verification_data,
            "pan_number": pan_number,
            "dob": dob
        }

        if verification_data.get('status') == 'verified':
            flash(f"PAN {pan_number} verified successfully: {verification_data.get('full_name')}", "success")
        else:
            flash(f"PAN verification failed: {verification_data.get('status_message')}", "danger")

        # Refresh recent checks after submit
        try:
            recent_checks = query.order_by(PANVerification.created_at.desc()).limit(50).all()
        except Exception:
            db.session.rollback()
            recent_checks = []

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


@pan_bp.route('/services/pan/<int:check_id>/json', methods=['GET'])
@login_required
def get_check_json(check_id):
    """Returns the full JSON payload for any PAN verification record."""
    company = current_user.company
    record = PANVerification.query.filter_by(id=check_id, company_id=company.id).first_or_404()
    return jsonify(record.to_dict())


@pan_bp.route('/api/pan', methods=['GET', 'POST'])
@pan_bp.route('/api/pan/<client_id>', methods=['GET', 'POST'])
@csrf.exempt
def public_api_pan(client_id=None):
    """
    Public REST API endpoint for PAN verification using CVL KRA GetPANStatus.
    Supports both universal (/api/pan) and company-dedicated (/api/pan/<client_id>) endpoints.
    Fetches CVL credentials from Company Profile and returns structured JSON.
    Can be called directly from Postman, cURL, or client applications.
    """
    company = None

    # 1. Resolve company if client_id is passed in the URL path
    target_client_id = (client_id or '').strip()
    if target_client_id:
        clean_no_hyphen = target_client_id.replace('-', '').upper()
        company = Company.query.filter(
            (db.func.upper(Company.client_id) == target_client_id.upper()) |
            (db.func.upper(db.func.replace(Company.client_id, '-', '')) == clean_no_hyphen)
        ).first()

        if not company:
            return jsonify({
                "success": False,
                "error": f"Invalid client ID: '{target_client_id}'. No active organisation found with this ID."
            }), 404

    # 2. Return API specification and documentation on GET request
    if request.method == 'GET':
        endpoint_url = f"/api/pan/{company.client_id}" if company else "/api/pan"
        headers_info = {"Content-Type": "application/json"}
        body_info = {
            "pan": "ABCDE1234F (Required - 10-character PAN number)",
            "dob": "DD/MM/YYYY (Required - Date of Birth)"
        }
        if not company:
            headers_info["X-API-Key"] = "YOUR_COMPANY_API_KEY (or client_id)"
            body_info["client_id"] = "YOUR_CLIENT_ID (Optional if not in URL)"

        return jsonify({
            "service": "ZoiKYC PAN Verification API",
            "method": "GetPANStatus",
            "company": company.name if company else "Universal",
            "client_id": company.client_id if company else None,
            "status": company.status if company else "active",
            "endpoint": endpoint_url,
            "http_method": "POST",
            "headers": headers_info,
            "body_params": body_info,
            "sample_request": {
                "pan": "HRQPB8013L",
                "dob": "26/11/2005"
            },
            "sample_curl": f"curl -X POST https://zoikyc.com{endpoint_url} -H 'Content-Type: application/json' -d '{{\"pan\": \"HRQPB8013L\", \"dob\": \"26/11/2005\"}}'"
        }), 200

    # 3. Read payload from JSON or Form body
    payload_data = request.get_json(silent=True) or {}
    if not payload_data and request.form:
        payload_data = request.form.to_dict()

    pan_number = (payload_data.get('pan') or payload_data.get('pan_number') or '').strip().upper()
    dob_day = str(payload_data.get('dob_day') or payload_data.get('day') or '').strip()
    dob_month = str(payload_data.get('dob_month') or payload_data.get('month') or '').strip()
    dob_year = str(payload_data.get('dob_year') or payload_data.get('year') or '').strip()
    if dob_day and dob_month and dob_year:
        dob = f"{dob_day.zfill(2)}/{dob_month.zfill(2)}/{dob_year}"
    else:
        dob = (payload_data.get('dob') or payload_data.get('date_of_birth') or '').strip()

    if not pan_number:
        return jsonify({
            "success": False,
            "status": "invalid",
            "error": "Missing required field: 'pan'. Please provide a 10-character PAN number."
        }), 400

    if not dob:
        return jsonify({
            "success": False,
            "status": "invalid",
            "error": "Missing required field: 'dob'. Date of Birth is required (format DD/MM/YYYY)."
        }), 400

    # 4. If company wasn't resolved via URL path, resolve from Headers or Body
    if not company:
        api_key = (
            request.headers.get('X-API-Key') or 
            request.headers.get('x-api-key') or 
            request.headers.get('api_key') or
            payload_data.get('api_key') or
            ""
        ).strip()

        body_client_id = (
            request.headers.get('X-Client-ID') or
            request.headers.get('x-client-id') or
            payload_data.get('client_id') or
            ""
        ).strip()

        auth_header = request.headers.get('Authorization', '').strip()
        if auth_header.lower().startswith('bearer '):
            api_key = auth_header[7:].strip()

        if api_key:
            clean_api_no_hyphen = api_key.replace('-', '').upper()
            company = Company.query.filter(
                (Company.api_key == api_key) | 
                (Company.client_id == api_key) |
                (db.func.upper(db.func.replace(Company.client_id, '-', '')) == clean_api_no_hyphen)
            ).first()
        
        if not company and body_client_id:
            clean_body_no_hyphen = body_client_id.replace('-', '').upper()
            company = Company.query.filter(
                (db.func.upper(Company.client_id) == body_client_id.upper()) |
                (db.func.upper(db.func.replace(Company.client_id, '-', '')) == clean_body_no_hyphen)
            ).first()

        if not company and current_user and current_user.is_authenticated:
            company = current_user.company

        # Fallback to the active company configured with CVL credentials
        if not company:
            company = Company.query.filter(
                Company.pos_code.isnot(None),
                Company.aes_key.isnot(None)
            ).first()

    # Call GetPANStatus gateway
    client_ip = _extract_client_ip()
    user_agent_str = (request.headers.get('User-Agent') or '')[:250]
    start_time = time.time()

    provider = PANVerificationProvider()
    verification_data = provider.verify_pan_with_dob(
        pan_number=pan_number,
        dob=dob,
        company=company
    )
    duration_ms = int((time.time() - start_time) * 1000)

    # If company is identified, record verification in database
    record_id = None
    if company:
        try:
            raw_resp_str = verification_data.get('raw_response')
            if not isinstance(raw_resp_str, str):
                raw_resp_str = json.dumps(raw_resp_str or {})

            record = PANVerification(
                company_id=company.id,
                user_id=current_user.id if current_user and current_user.is_authenticated else None,
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
                cost_charged=Decimal('0.00'),
                reference_id=verification_data.get('reference_id'),
                raw_response=raw_resp_str,
                raw_request=verification_data.get('raw_request'),
                ip_address=client_ip,
                method=verification_data.get('method', 'CVL KRA'),
                endpoint=request.path,
                user_agent=user_agent_str,
                duration_ms=duration_ms
            )
            db.session.add(record)
            db.session.commit()
            record_id = record.id
        except Exception:
            db.session.rollback()

    status_code = 200 if verification_data.get('success') else 400 if verification_data.get('status') == 'invalid' else 200

    return jsonify({
        "success": verification_data.get('success', False),
        "status": verification_data.get('status'),
        "pan": pan_number,
        "full_name": verification_data.get('full_name'),
        "first_name": verification_data.get('first_name'),
        "middle_name": verification_data.get('middle_name'),
        "last_name": verification_data.get('last_name'),
        "category": verification_data.get('category'),
        "pan_status": verification_data.get('pan_status'),
        "dob_match": verification_data.get('dob_match'),
        "aadhaar_seeding": verification_data.get('aadhaar_seeding_status'),
        "status_message": verification_data.get('status_message'),
        "reference_id": verification_data.get('reference_id'),
        "record_id": record_id,
        "method": verification_data.get('method', 'GetPANStatus'),
        "company": company.name if company else None,
        "client_id": company.client_id if company else None,
        "ip_address": client_ip,
        "duration_ms": duration_ms,
        "raw_response": verification_data.get('raw_response')
    }), status_code


