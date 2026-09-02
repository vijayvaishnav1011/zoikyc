import os
import uuid
import razorpay
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime, timezone
from flask import current_app
from app.extensions import db
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction

PLATFORM_FEE_PERCENT = Decimal('0.02') # 2% Platform Fee

def calculate_recharge_amounts(base_amount_inr):
    """
    Calculates 2% platform fee and total payable amount.
    Returns (base_amount, platform_fee, total_payable).
    """
    base_amount = Decimal(str(base_amount_inr)).quantize(Decimal('0.01'))
    platform_fee = (base_amount * PLATFORM_FEE_PERCENT).quantize(Decimal('0.01'))
    total_payable = base_amount + platform_fee
    return base_amount, platform_fee, total_payable

def get_razorpay_client():
    load_dotenv(override=True)
    key_id = os.environ.get('RAZORPAY_KEY_ID') or current_app.config.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET') or current_app.config.get('RAZORPAY_KEY_SECRET')
    if key_id and key_secret:
        return razorpay.Client(auth=(key_id.strip(), key_secret.strip()))
    return None

def create_razorpay_order(amount_inr, company_id, company_name=None):
    """
    Creates a new Razorpay Order for online wallet recharge including a 2% platform fee.
    Amount in Razorpay is specified in paise (1 INR = 100 paise).
    """
    client = get_razorpay_client()
    if not client:
        return None, "Razorpay API credentials not configured.", None, None, None

    try:
        base_amount, platform_fee, total_payable = calculate_recharge_amounts(amount_inr)
        amount_paise = int(total_payable * 100)
        order_data = {
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'company_id': str(company_id),
                'company_name': str(company_name or ''),
                'base_amount': str(base_amount),
                'platform_fee': str(platform_fee),
                'total_payable': str(total_payable)
            }
        }
        order = client.order.create(data=order_data)
        return order, None, base_amount, platform_fee, total_payable
    except Exception as e:
        return None, str(e), None, None, None

def verify_razorpay_payment(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Cryptographically verifies the Razorpay payment signature.
    """
    client = get_razorpay_client()
    if not client:
        return False, "Razorpay client not configured."

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        return True, "Payment signature verified successfully."
    except razorpay.errors.SignatureVerificationError:
        return False, "Cryptographic signature verification failed."
    except Exception as e:
        return False, str(e)

def process_wallet_recharge(company_id, amount, payment_method='razorpay', reference_id=None, reference_prefix='RECH', description=None):
    """
    Atomically credits a company wallet and logs an immutable ledger transaction entry.
    Uses pessimistic locking (with_for_update) to prevent race conditions.
    Returns (success, transaction, message).
    """
    amount = Decimal(str(amount))
    if amount <= Decimal('0.00'):
        return False, None, "Invalid amount. Recharge amount must be positive."

    try:
        # Lock wallet row for safe atomic balance calculation
        wallet = db.session.query(Wallet).filter_by(company_id=company_id).with_for_update().first()
        
        if not wallet:
            return False, None, "Wallet not found for company."

        if wallet.status != 'active':
            return False, None, f"Wallet is currently {wallet.status}. Transaction rejected."

        balance_before = wallet.balance
        balance_after = balance_before + amount

        # Update wallet balance
        wallet.balance = balance_after
        wallet.updated_at = datetime.now(timezone.utc)

        # Unique reference ID
        unique_ref = reference_id or f"{reference_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"

        # Create Ledger Transaction Record
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            company_id=company_id,
            type='credit',
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_id=unique_ref,
            status='success',
            description=description or f"Wallet Recharge via {payment_method.upper()}"
        )

        db.session.add(transaction)
        db.session.commit()
        return True, transaction, "Wallet successfully credited!"

    except Exception as e:
        db.session.rollback()
        return False, None, f"Failed to process transaction: {str(e)}"
