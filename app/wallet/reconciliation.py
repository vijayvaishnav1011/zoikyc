"""
Wallet Reconciliation Service
==============================
Matches pending Razorpay orders against live Razorpay API status and
credits the wallet for any captured/authorized payments that were missed
due to dropped webhooks or browser disconnections.

Usage:
  - As a Flask CLI command:  flask wallet reconcile-pending
  - Automatically as a background thread every 10 minutes (via app factory)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def reconcile_pending_recharges(app=None):
    """
    Main reconciliation function. Fetches all pending PendingRecharge records
    older than 2 minutes (give the normal flow time to complete), then checks
    each against Razorpay API. Captured orders are credited; failed/expired
    orders are marked accordingly.

    Returns (credited_count, failed_count, skipped_count)
    """
    from app.extensions import db
    from app.models.pending_recharge import PendingRecharge
    from app.wallet.services import get_razorpay_client, process_wallet_recharge

    ctx = app.app_context() if app else None
    if ctx:
        ctx.push()

    credited = 0
    failed = 0
    skipped = 0

    try:
        client = get_razorpay_client()
        if not client:
            logger.warning("[RECONCILE] Razorpay client not configured. Skipping.")
            return 0, 0, 0

        # Only reconcile pending orders created more than 2 min ago (normal flow needs time)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)

        pending_records = (
            PendingRecharge.query
            .filter(
                PendingRecharge.status == 'pending',
                PendingRecharge.created_at <= cutoff
            )
            .order_by(PendingRecharge.created_at.asc())
            .limit(50)
            .all()
        )

        logger.info(f"[RECONCILE] Found {len(pending_records)} pending recharges to reconcile.")

        for record in pending_records:
            try:
                # Fetch order payments from Razorpay
                order_payments = client.order.payments(record.razorpay_order_id)
                items = order_payments.get('items', []) if order_payments else []

                if not items:
                    # Order exists but no payment attempt yet — check if expired (>1 day)
                    age = datetime.now(timezone.utc) - record.created_at.replace(tzinfo=timezone.utc)
                    if age > timedelta(hours=24):
                        record.status = 'expired'
                        record.failure_reason = 'No payment attempt within 24 hours.'
                        record.updated_at = datetime.now(timezone.utc)
                        db.session.add(record)
                        failed += 1
                        logger.info(f"[RECONCILE] Order {record.razorpay_order_id} expired (no payment in 24h).")
                    else:
                        skipped += 1
                    continue

                # Get the most recent payment for this order
                payment = items[-1]
                payment_id = payment.get('id')
                status = payment.get('status')

                if status == 'authorized':
                    # Capture the payment
                    try:
                        captured = client.payment.capture(payment_id, payment.get('amount'))
                        status = captured.get('status', status)
                        logger.info(f"[RECONCILE] Captured authorized payment {payment_id}.")
                    except Exception as cap_err:
                        logger.warning(f"[RECONCILE] Could not capture {payment_id}: {cap_err}")

                if status == 'captured':
                    # Check if already credited
                    from app.models.transaction import WalletTransaction
                    already = WalletTransaction.query.filter_by(reference_id=payment_id).first()
                    if already:
                        record.status = 'captured'
                        record.razorpay_payment_id = payment_id
                        record.updated_at = datetime.now(timezone.utc)
                        db.session.add(record)
                        skipped += 1
                        logger.info(f"[RECONCILE] Payment {payment_id} already credited. Marked captured.")
                        continue

                    # Credit wallet
                    success, txn, msg = process_wallet_recharge(
                        company_id=record.company_id,
                        amount=record.base_amount,
                        payment_method='razorpay',
                        reference_id=payment_id,
                        description=f"Wallet Recharge via Razorpay [Auto-Reconciled] ({payment_id})"
                    )

                    record.razorpay_payment_id = payment_id
                    record.updated_at = datetime.now(timezone.utc)

                    if success:
                        record.status = 'captured'
                        db.session.add(record)
                        credited += 1
                        logger.info(
                            f"[RECONCILE] ✅ Credited ₹{record.base_amount} to company "
                            f"{record.company_id} for payment {payment_id}."
                        )
                    else:
                        record.status = 'pending'  # Keep pending so we retry next run
                        record.failure_reason = msg[:255]
                        db.session.add(record)
                        logger.error(f"[RECONCILE] ❌ Failed to credit wallet for {payment_id}: {msg}")

                elif status in ('failed', 'refunded'):
                    record.status = 'failed'
                    record.razorpay_payment_id = payment_id
                    record.failure_reason = (
                        payment.get('error_description') or
                        payment.get('description') or
                        f"Payment {status}"
                    )[:255]
                    record.updated_at = datetime.now(timezone.utc)
                    db.session.add(record)
                    failed += 1
                    logger.info(f"[RECONCILE] Payment {payment_id} is {status}. Marked failed.")

                else:
                    # created / pending — still in progress
                    skipped += 1
                    logger.debug(f"[RECONCILE] Payment {payment_id} still in status '{status}'. Skipping.")

            except Exception as rec_err:
                logger.error(
                    f"[RECONCILE] Error processing order {record.razorpay_order_id}: {rec_err}"
                )
                skipped += 1

        db.session.commit()
        logger.info(
            f"[RECONCILE] Done. Credited={credited}, Failed={failed}, Skipped={skipped}"
        )
        return credited, failed, skipped

    except Exception as e:
        logger.error(f"[RECONCILE] Fatal reconciliation error: {e}")
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return 0, 0, 0
    finally:
        if ctx:
            ctx.pop()


def start_background_reconciler(app):
    """
    Starts a daemon background thread that runs reconcile_pending_recharges()
    every 10 minutes. Called once from the app factory.
    """
    import threading

    def _runner():
        import time
        logger.info("[RECONCILE SCHEDULER] Background reconciler started (interval: 10 min).")
        while True:
            time.sleep(600)  # Wait 10 minutes between runs
            try:
                with app.app_context():
                    credited, failed, skipped = reconcile_pending_recharges()
                    if credited > 0:
                        logger.info(
                            f"[RECONCILE SCHEDULER] Auto-credited {credited} wallet(s) this cycle."
                        )
            except Exception as e:
                logger.error(f"[RECONCILE SCHEDULER] Error in background run: {e}")

    t = threading.Thread(target=_runner, name="WalletReconciler", daemon=True)
    t.start()
    return t
