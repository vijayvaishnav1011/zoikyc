import os
import uuid
import smtplib
import threading
import razorpay
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime, timezone
from flask import current_app, render_template
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
            description=description or "Wallet Recharge via Razorpay"
        )

        db.session.add(transaction)
        db.session.commit()
        return True, transaction, "Wallet successfully credited!"

    except Exception as e:
        db.session.rollback()
        return False, None, f"Failed to process transaction: {str(e)}"


from email.mime.application import MIMEApplication
from app.wallet.invoice import generate_recharge_pdf_invoice

def _async_send_recharge_email_task(app, to_email, user_name, company_name, client_id, gstin, address, amount, platform_fee, total_paid, updated_balance, reference_id, txn_date):
    """Worker task that dispatches responsive confirmation receipt email with PDF Tax Invoice attachment."""
    with app.app_context():
        smtp_server = os.environ.get("MAIL_SERVER", "smtp.hostinger.com")
        port = int(os.environ.get("MAIL_PORT", 465))
        sender_email = os.environ.get("MAIL_USERNAME", "info@zoikyc.com")
        password = os.environ.get("MAIL_PASSWORD", "Zoikyc@32132321")

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"Wallet Recharge Successful — ₹{amount:,.2f} Credited | ZoiKYC"
        msg["From"] = f"ZoiKYC <{sender_email}>"
        msg["To"] = to_email

        # Body Alternative Container
        alt_part = MIMEMultipart("alternative")
        try:
            html_content = render_template(
                'email/wallet_recharge_success.html',
                user_name=user_name,
                company_name=company_name,
                amount=amount,
                platform_fee=platform_fee,
                total_paid=total_paid,
                updated_balance=updated_balance,
                reference_id=reference_id,
                txn_date=txn_date
            )
        except Exception as te:
            print(f"⚠️ Recharge email template render notice: {te}")
            html_content = f"<h2>Wallet Recharge Successful: ₹{amount:,.2f} credited. Ref: {reference_id}</h2>"

        alt_part.attach(MIMEText(html_content, "html"))
        msg.attach(alt_part)

        # Generate and attach PDF Tax Invoice / Receipt
        try:
            pdf_data = generate_recharge_pdf_invoice(
                company_name=company_name,
                client_id=client_id,
                gstin=gstin,
                address=address,
                user_name=user_name,
                amount=amount,
                platform_fee=platform_fee,
                total_paid=total_paid,
                reference_id=reference_id,
                txn_date=txn_date
            )
            pdf_attachment = MIMEApplication(pdf_data, _subtype="pdf")
            filename = f"ZoiKYC_Invoice_{reference_id}.pdf"
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(pdf_attachment)
            print(f"📄 Attached PDF Invoice: {filename}")
        except Exception as pe:
            print(f"⚠️ PDF Invoice generation failed: {pe}")

        try:
            with smtplib.SMTP_SSL(smtp_server, port, timeout=15) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, to_email, msg.as_string())
            print(f"✅ [RECHARGE EMAIL + PDF SUCCESS] Sent confirmation receipt & PDF invoice to {to_email}")
        except Exception as e:
            print(f"❌ [RECHARGE EMAIL FAIL] Failed sending to {to_email}: {str(e)}")


def send_wallet_recharge_email(to_email, user_name, company_name, amount, platform_fee, total_paid, updated_balance, reference_id, client_id=None, gstin=None, address=None):
    """
    Asynchronously dispatches a branded HTML email confirmation and PDF invoice to the user upon wallet recharge.
    """
    app = current_app._get_current_object()
    txn_date = datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    thread = threading.Thread(
        target=_async_send_recharge_email_task,
        args=(app, to_email, user_name, company_name, client_id, gstin, address, amount, platform_fee, total_paid, updated_balance, reference_id, txn_date)
    )
    thread.daemon = True
    thread.start()
    return True


def _async_send_low_balance_task(app, to_email, user_name, company_name, client_id, balance):
    """Worker task that dispatches a low wallet balance warning email."""
    with app.app_context():
        smtp_server = os.environ.get("MAIL_SERVER", "smtp.hostinger.com")
        port = int(os.environ.get("MAIL_PORT", 465))
        sender_email = os.environ.get("MAIL_USERNAME", "info@zoikyc.com")
        password = os.environ.get("MAIL_PASSWORD", "Zoikyc@32132321")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Action Required: Low Wallet Balance Alert (₹{balance:,.2f}) — ZoiKYC"
        msg["From"] = f"ZoiKYC <{sender_email}>"
        msg["To"] = to_email

        try:
            html_content = render_template(
                'email/low_wallet_balance_alert.html',
                user_name=user_name,
                company_name=company_name,
                client_id=client_id,
                balance=balance
            )
        except Exception as te:
            print(f"⚠️ Low balance template error: {te}")
            html_content = f"<h2>Action Required: Low Wallet Balance Alert</h2><p>Your wallet balance is ₹{balance:,.2f}. Please recharge at https://zoikyc.com/wallet/recharge</p>"

        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL(smtp_server, port, timeout=15) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, to_email, msg.as_string())
            print(f"✅ [LOW BALANCE ALERT SUCCESS] Sent low balance notice to {to_email}")
        except Exception as e:
            print(f"❌ [LOW BALANCE ALERT FAIL] Failed sending to {to_email}: {str(e)}")


def send_low_balance_alert_email(to_email, user_name, company_name, client_id, balance):
    """
    Asynchronously dispatches a branded Low Wallet Balance Alert email to a company.
    """
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_async_send_low_balance_task,
        args=(app, to_email, user_name, company_name, client_id, balance)
    )
    thread.daemon = True
    thread.start()
    return True



