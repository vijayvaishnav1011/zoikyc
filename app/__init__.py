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
    @app.template_filter('currency')
    def format_currency(value):
        if value is None:
            return "₹0.00"
        try:
            val = float(value)
            return f"₹{val:,.2f}"
        except (ValueError, TypeError):
            return "₹0.00"

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
