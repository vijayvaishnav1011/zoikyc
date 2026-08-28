from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.wallet import wallet_bp
from app.wallet.forms import RechargeWalletForm
from app.wallet.services import process_wallet_recharge
from app.models.transaction import WalletTransaction

@wallet_bp.route('/wallet')
@login_required
def index():
    company = current_user.company
    wallet = company.wallet if company else None
    
    # Recent 5 transactions for quick view
    transactions = WalletTransaction.query.filter_by(
        company_id=current_user.company_id
    ).order_by(WalletTransaction.created_at.desc()).limit(5).all()

    return render_template('wallet/index.html', wallet=wallet, company=company, transactions=transactions)

@wallet_bp.route('/wallet/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    txn_type = request.args.get('type', 'all', type=str)

    query = WalletTransaction.query.filter_by(company_id=current_user.company_id)
    
    if txn_type in ['credit', 'debit']:
        query = query.filter_by(type=txn_type)

    pagination = query.order_by(WalletTransaction.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )

    return render_template(
        'wallet/transactions.html',
        pagination=pagination,
        transactions=pagination.items,
        txn_type=txn_type
    )

@wallet_bp.route('/wallet/recharge', methods=['GET', 'POST'])
@login_required
def recharge():
    form = RechargeWalletForm()
    wallet = current_user.company.wallet if current_user.company else None

    if form.validate_on_submit():
        amount = form.amount.data
        payment_method = form.payment_method.data

        # Execute atomic server-side recharge transaction
        success, txn, msg = process_wallet_recharge(
            company_id=current_user.company_id,
            amount=amount,
            payment_method=payment_method
        )

        if success:
            flash(f"Payment successful! ₹{amount:,.2f} credited to your wallet. Reference: {txn.reference_id}", "success")
            return redirect(url_for('wallet.index'))
        else:
            flash(f"Payment failed: {msg}", "danger")

    return render_template('wallet/recharge.html', form=form, wallet=wallet)
