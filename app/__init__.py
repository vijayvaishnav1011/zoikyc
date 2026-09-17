import os
from flask import Flask, redirect, url_for, render_template
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import config_by_name
from app.extensions import db, migrate, login_manager, csrf

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    # Support reverse proxy headers (Traefik / Cloudflare) to prevent redirect loops
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register Jinja2 filters
    from app.utils.timezone import to_ist, format_ist

    @app.template_filter('currency')
    def format_currency(value):
        if value is None:
            return "₹0.00"
        try:
            val = float(value)
            return f"₹{val:,.2f}"
        except (ValueError, TypeError):
            return "₹0.00"

    @app.template_filter('to_ist')
    def jinja_to_ist(value, fmt=None):
        return to_ist(value, fmt=fmt)

    @app.template_filter('ist_datetime')
    def jinja_ist_datetime(value, fmt="%d %b %Y, %I:%M %p"):
        return format_ist(value, fmt=fmt)

    @app.template_filter('ist_date')
    def jinja_ist_date(value, fmt="%d %b %Y"):
        return format_ist(value, fmt=fmt)

    @app.template_filter('ist_time')
    def jinja_ist_time(value, fmt="%I:%M %p"):
        return format_ist(value, fmt=fmt)

    # Register Blueprints
    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.wallet import wallet_bp
    from app.company import company_bp
    from app.admin import admin_bp
    from app.esign import esign_bp
    from app.pan import pan_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(esign_bp)
    app.register_blueprint(pan_bp)

    # Health check endpoint
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'service': 'ZoiKYC'}, 200

    # Diagnostic deployment version endpoint
    @app.route('/version')
    def version_check():
        pypdf_ok = False
        pypdf_ver = None
        try:
            import pypdf
            pypdf_ok = True
            pypdf_ver = getattr(pypdf, '__version__', 'installed')
        except ImportError:
            pass
        return {
            'version': '2.1.2',
            'pypdf_installed': pypdf_ok,
            'pypdf_version': pypdf_ver,
            'service': 'ZoiKYC'
        }, 200

    @app.route('/debug-pdf', methods=['POST'])
    @csrf.exempt
    def debug_pdf():
        import traceback, base64, io, requests
        from flask import request, jsonify
        data = request.get_json(silent=True) or {}
        raw_b64 = (data.get('file_base64') or data.get('pdf_base64') or '').strip()
        if ',' in raw_b64 and 'base64' in raw_b64[:60]:
            raw_b64 = raw_b64.split(',', 1)[1].strip()
        
        info = {}
        try:
            pdf_bytes = base64.b64decode(raw_b64)
            info["original_len"] = len(pdf_bytes)
            info["starts_with_pdf"] = pdf_bytes.startswith(b'%PDF')
            
            import pypdf
            info["pypdf_version"] = getattr(pypdf, '__version__', 'unknown')
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            info["pages"] = len(reader.pages)
            info["is_encrypted"] = reader.is_encrypted
            writer = pypdf.PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            out = io.BytesIO()
            writer.write(out)
            sanitized_bytes = out.getvalue()
            info["sanitized_len"] = len(sanitized_bytes)
            info["sanitized_starts_with_pdf"] = sanitized_bytes.startswith(b'%PDF')
            
            from app.integrations.capricorn import CapricornESignProvider
            provider = CapricornESignProvider()
            clean_b64_str = base64.b64encode(sanitized_bytes).decode('utf-8')
            txn_id = provider.generate_unique_txn()
            capricorn_payload = {
                'request': {
                    'auth': {'token': provider.token, 'key': provider.key, 'command': 'esign'},
                    'parameter': {
                        'uploadpdf': {
                            'pdf64': clean_b64_str,
                            'pdfurl': '',
                            'title': 'Debug Agreement',
                            'txn': txn_id,
                            'callbackurl': 'https://zoikyc.com/esign/callback',
                            'signatories': {
                                'signatory': {
                                    'id': 'signatory1',
                                    'name': data.get('signatory_name', 'Pankaj Vaishnav'),
                                    'email': 'no-reply@zoikyc.com',
                                    'mail': '',
                                    'mobile': '',
                                    'sms': '',
                                    'mode': 'online-aadhaar-otp',
                                    'ekycid': 'esignnetwork',
                                    'dsc': {'email': '', 'serial': '', 'organization': '', 'orgunit': ''},
                                    'option': {
                                        'cood': data.get('cood', '400,20,550,90'),
                                        'pagenum': data.get('page_num', 'all'),
                                        'reason': 'Agreement sign',
                                        'location': 'Delhi',
                                        'customtext': f"Signed by {data.get('signatory_name', 'Pankaj Vaishnav')}",
                                        'enableltv': '', 'lockpdf': '', 'enablets': '', 'includesubject': '', 'includecn': ''
                                    }
                                }
                            }
                        }
                    }
                }
            }
            cap_resp = requests.post(provider.api_url, json=capricorn_payload, timeout=30)
            info["capricorn_http_code"] = cap_resp.status_code
            info["capricorn_response"] = cap_resp.json()
        except Exception as ex:
            info["exception"] = str(ex)
            info["traceback"] = traceback.format_exc()
            
        return jsonify(info), 200


    # Root route - Public Landing Page for zoikyc.com
    @app.route('/')
    def landing():
        from flask_login import current_user
        if current_user.is_authenticated:
            if current_user.role == 'super_admin':
                return redirect(url_for('admin.index'))
            return redirect(url_for('dashboard.index'))
        return render_template('landing.html')

    # Auto-create missing database tables & seed Super Admin on startup
    with app.app_context():
        try:
            from sqlalchemy import text
            def _safe_ddl(stmt):
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text(stmt))
                        conn.commit()
                except Exception:
                    pass

            # Companies columns
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS client_id VARCHAR(50);")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS per_kyc_price NUMERIC(10, 2) DEFAULT 20.00;")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS min_recharge_amount NUMERIC(10, 2) DEFAULT 1000.00;")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS pos_code VARCHAR(100);")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS api_user_id VARCHAR(100);")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS api_password VARCHAR(255);")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS aes_key VARCHAR(255);")
            _safe_ddl("ALTER TABLE companies ADD COLUMN IF NOT EXISTS api_key VARCHAR(255);")

            from app.models.esign import ESignDocument
            from app.models.pending_recharge import PendingRecharge  # ensure table exists
            db.create_all()

            # Pending recharges columns
            _safe_ddl("ALTER TABLE pending_recharges ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(255);")

            # PAN verifications columns
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS raw_request TEXT;")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS raw_response TEXT;")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS dob VARCHAR(20);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS reference_id VARCHAR(100);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS aadhaar_seeding_status VARCHAR(100);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS pan_status VARCHAR(50);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS dob_match BOOLEAN;")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS ip_address VARCHAR(100);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS method VARCHAR(100);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS endpoint VARCHAR(255);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255);")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS duration_ms INTEGER;")
            _safe_ddl("ALTER TABLE pan_verifications ADD COLUMN IF NOT EXISTS server_ip VARCHAR(100) DEFAULT '187.127.139.6';")
            _safe_ddl("UPDATE pan_verifications SET server_ip = '187.127.139.6' WHERE server_ip IS NULL;")

            # E-Sign documents audit log columns
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS raw_request TEXT;")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS raw_response TEXT;")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS ip_address VARCHAR(100);")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS method VARCHAR(100);")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS endpoint VARCHAR(255);")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255);")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS duration_ms INTEGER;")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS server_ip VARCHAR(100) DEFAULT '187.127.139.6';")
            _safe_ddl("ALTER TABLE esign_documents ADD COLUMN IF NOT EXISTS callback_url VARCHAR(500);")
            _safe_ddl("UPDATE esign_documents SET server_ip = '187.127.139.6' WHERE server_ip IS NULL;")
            from app.models.company import Company
            from app.models.user import User
            from app.models.wallet import Wallet
            from app.auth.services import generate_unique_client_id

            # Auto-backfill or standardize all companies to ZOI-<letters>-<15 digits> client_id format
            try:
                import re
                client_id_regex = re.compile(r'^ZOI-[A-Z0-9]{2}-\d{15}$')
                all_comps = Company.query.all()
                updated_any = False
                for comp in all_comps:
                    if not comp.client_id or not client_id_regex.match(comp.client_id):
                        comp.client_id = generate_unique_client_id(comp.name)
                        updated_any = True
                if updated_any:
                    db.session.commit()
            except Exception as be:
                db.session.rollback()

            # Seed default exclusive Super Admin (info@zoikyc.com)
            admin_user = User.query.filter_by(email='info@zoikyc.com').first()
            if not admin_user:
                # Ensure Master Platform Company exists
                master_company = Company.query.filter_by(email='info@zoikyc.com').first()
                if not master_company:
                    master_company = Company(
                        name='ZoiKYC Platform Admin',
                        authorised_signatory_name='Platform Master',
                        email='info@zoikyc.com',
                        phone='+91 9999999999',
                        country='India',
                        state='Delhi',
                        city='New Delhi',
                        zip_code='110001',
                        gstin='07AAAAA0000A1Z0',
                        address='ZoiKYC Operations HQ',
                        status='active'
                    )
                    db.session.add(master_company)
                    db.session.flush()

                    master_wallet = Wallet(company_id=master_company.id)
                    db.session.add(master_wallet)

                admin_user = User(
                    company_id=master_company.id,
                    name='Super Admin',
                    email='info@zoikyc.com',
                    phone='+91 9999999999',
                    role='super_admin',
                    email_verified=True,
                    status='active'
                )
                admin_user.set_password('Admin@32132321')
                db.session.add(admin_user)
                db.session.commit()
                app.logger.info("Default Super Admin created: info@zoikyc.com")
            else:
                # Ensure credentials and super_admin role
                admin_user.role = 'super_admin'
                admin_user.email_verified = True
                admin_user.status = 'active'
                admin_user.set_password('Admin@32132321')
                db.session.commit()

            # Ensure only info@zoikyc.com has super_admin power; all other users are clients
            User.query.filter(User.email != 'info@zoikyc.com', User.role == 'super_admin').update({'role': 'company_admin'})
            db.session.commit()

        except Exception as e:
            app.logger.warning(f"Auto db initialization notice: {e}")

    # Start background wallet reconciliation scheduler (daemon thread)
    # Runs every 10 minutes to sync pending Razorpay orders with wallet credits
    try:
        # Only run in the main process (not in Flask reloader child process)
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'false':
            from app.wallet.reconciliation import start_background_reconciler
            start_background_reconciler(app)
            app.logger.info("[WALLET] Background reconciler thread started (10-min cycle).")
    except Exception as sched_err:

        app.logger.warning(f"[WALLET] Could not start background reconciler: {sched_err}")

    return app
