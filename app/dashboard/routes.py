from flask import render_template
from flask_login import login_required, current_user
from app.dashboard import dashboard_bp
from app.models.transaction import WalletTransaction

@dashboard_bp.route('/dashboard')
@login_required
def index():
    company = current_user.company
    wallet = company.wallet if company else None
    recent_transactions = []
    
    if company:
        recent_transactions = WalletTransaction.query.filter_by(
            company_id=company.id
        ).order_by(WalletTransaction.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard/index.html',
        company=company,
        wallet=wallet,
        recent_transactions=recent_transactions
    )
