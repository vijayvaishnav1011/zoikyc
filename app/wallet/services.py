import uuid
from decimal import Decimal
from datetime import datetime, timezone
from app.extensions import db
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction

def process_wallet_recharge(company_id, amount, payment_method='mock_gateway', reference_prefix='RECH'):
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

        # Generate unique reference ID
        unique_ref = f"{reference_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"

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
