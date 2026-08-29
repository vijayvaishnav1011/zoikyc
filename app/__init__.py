import os
from flask import Flask, redirect, url_for
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(company_bp)

    # Health check endpoint
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'service': 'ZoiKYC'}, 200

    # Root route redirect
    @app.route('/')
    def index_redirect():
        return redirect(url_for('dashboard.index'))

    # Auto-create missing database tables on app startup
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning(f"Auto db.create_all notice: {e}")

    return app
