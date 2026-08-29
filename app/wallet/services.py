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

def get_razorpay_client():
    load_dotenv(override=True)
    key_id = os.environ.get('RAZORPAY_KEY_ID') or current_app.config.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET') or current_app.config.get('RAZORPAY_KEY_SECRET')
    if key_id and key_secret:
        return razorpay.Client(auth=(key_id.strip(), key_secret.strip()))
    return None

def create_razorpay_order(amount_inr, company_id, company_name=None):
    """
    Creates a new Razorpay Order for online wallet recharge.
    Amount in Razorpay is specified in paise (1 INR = 100 paise).
    """
    client = get_razorpay_client()
    if not client:
        return None, "Razorpay API credentials not configured."

    try:
        amount_paise = int(Decimal(str(amount_inr)) * 100)
        order_data = {
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'company_id': str(company_id),
                'company_name': str(company_name or '')
            }
        }
        order = client.order.create(data=order_data)
        return order, None
    except Exception as e:
        return None, str(e)

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

def process_wallet_recharge(company_id, amount, payment_method='razorpay', reference_id=None, reference_prefix='RECH'):
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
            description=f"Wallet Recharge via {payment_method.upper()}"
        )

        db.session.add(transaction)
        db.session.commit()
        return True, transaction, "Wallet successfully credited!"

    except Exception as e:
        db.session.rollback()
        return False, None, f"Failed to process transaction: {str(e)}"
