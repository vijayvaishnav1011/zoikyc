import os
import json
from decimal import Decimal
from dotenv import load_dotenv
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.wallet import wallet_bp
from app.wallet.forms import RechargeWalletForm
from app.wallet.services import (
    process_wallet_recharge,
    create_razorpay_order,
    verify_razorpay_payment,
    calculate_recharge_amounts,
    send_wallet_recharge_email
)
from app.models.transaction import WalletTransaction
from app.models.setting import get_platform_fee_config

def get_current_razorpay_key():
    load_dotenv(override=True)
    return (os.environ.get('RAZORPAY_KEY_ID') or current_app.config.get('RAZORPAY_KEY_ID', '')).strip()

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
    key_id = get_current_razorpay_key()
    fee_percent, fee_name = get_platform_fee_config()

    return render_template(
        'wallet/recharge.html',
        form=form,
        wallet=wallet,
        razorpay_key_id=key_id,
        fee_percent=fee_percent,
        fee_name=fee_name
    )

@wallet_bp.route('/wallet/create-razorpay-order', methods=['POST'])
@login_required
def create_order():
    try:
        data = request.get_json(silent=True) or request.form
        amount_val = data.get('amount', 1000)
        amount = Decimal(str(amount_val))
        
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Amount must be greater than zero.'}), 400

        company = current_user.company
        key_id = get_current_razorpay_key()
        fee_percent, fee_name = get_platform_fee_config()

        # Create Order with Razorpay SDK (including configured Platform Fee)
        order, err, base_amount, platform_fee, total_payable = create_razorpay_order(amount, company.id, company.name)
        
        if order:
            return jsonify({
                'success': True,
                'order_id': order['id'],
                'amount': order['amount'],
                'base_amount': float(base_amount),
                'platform_fee': float(platform_fee),
                'fee_percent': float(fee_percent),
                'fee_name': fee_name,
                'total_payable': float(total_payable),
                'currency': order.get('currency', 'INR'),
                'key_id': key_id,
                'company_name': company.name,
                'user_name': current_user.name,
                'user_email': current_user.email,
                'user_phone': current_user.phone
            })
        else:
            return jsonify({'success': False, 'message': f"Order creation error: {err}"}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@wallet_bp.route('/wallet/verify-razorpay-payment', methods=['POST'])
@login_required
def verify_payment():
    try:
        data = request.get_json(silent=True) or request.form
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_signature = data.get('razorpay_signature')
        amount = Decimal(str(data.get('amount', '0.00')))

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return jsonify({'success': False, 'message': 'Missing signature parameters.'}), 400

        # Cryptographically verify signature
        verified, msg = verify_razorpay_payment(
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature
        )

        if not verified:
            return jsonify({'success': False, 'message': f"Security verification failed: {msg}"}), 400

        # Calculate base recharge amount (wallet credit) and 2% platform fee
        base_amount, platform_fee, total_payable = calculate_recharge_amounts(amount)

        # Atomically credit company wallet with the base recharge amount
        success, txn, msg = process_wallet_recharge(
            company_id=current_user.company_id,
            amount=base_amount,
            payment_method='razorpay',
            reference_id=razorpay_payment_id,
            description="Wallet Recharge via Razorpay"
        )

        if success:
            # Asynchronously dispatch confirmation receipt email and PDF invoice to user's mailbox
            try:
                comp = current_user.company
                send_wallet_recharge_email(
                    to_email=current_user.email,
                    user_name=current_user.name,
                    company_name=comp.name if comp else "Organisation",
                    client_id=comp.client_id if comp else None,
                    gstin=comp.gstin if comp else None,
                    address=comp.address if comp else None,
                    amount=base_amount,
                    platform_fee=platform_fee,
                    total_paid=total_payable,
                    updated_balance=txn.balance_after,
                    reference_id=razorpay_payment_id
                )
            except Exception as mail_err:
                current_app.logger.warning(f"Recharge email dispatch error: {mail_err}")

            flash(f"Payment Verified! ₹{base_amount:,.2f} credited to your wallet. (Ref: {razorpay_payment_id})", "success")
            return jsonify({
                'success': True,
                'message': 'Wallet successfully credited!',
                'reference_id': razorpay_payment_id,
                'redirect_url': url_for('wallet.index')
            })
        else:
            return jsonify({'success': False, 'message': msg}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
