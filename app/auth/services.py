import os
import random
import string
import smtplib
import base64
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import current_app, render_template
from app.extensions import db
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet

def generate_otp():
    """Generate a random 6-digit numeric OTP."""
    return ''.join(random.choices(string.digits, k=6))


def _async_send_email_task(app, to_email, otp_code, user_name):
    """Internal worker task that sends clean HTML email without attachment chips."""
    with app.app_context():
        smtp_server = os.environ.get("MAIL_SERVER", "smtpout.secureserver.net")
        port = int(os.environ.get("MAIL_PORT", 465))
        sender_email = os.environ.get("MAIL_USERNAME", "info@zoibit.com")
        password = os.environ.get("MAIL_PASSWORD", "Admin@12312123")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ZoiKYC Email Verification Code: {otp_code}"
        msg["From"] = f"ZoiKYC <{sender_email}>"
        msg["To"] = to_email

        try:
            html_content = render_template('email/otp_verification.html', otp_code=otp_code, user_name=user_name, to_email=to_email)
        except Exception as te:
            print(f"⚠️ Template render error: {str(te)}")
            html_content = f"<h2>ZoiKYC OTP: {otp_code}</h2>"

        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL(smtp_server, port, timeout=15) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, to_email, msg.as_string())
            print(f"✅ [REAL SMTP SUCCESS] Sent clean email (no attachment chip) to {to_email}")
        except Exception as e:
            print(f"❌ [SMTP FAIL] Failed sending email to {to_email}: {str(e)}")


def send_real_otp_email(to_email, otp_code, user_name="Valued Client"):
    """
    Spawns an asynchronous background thread to send real HTML OTP email instantly
    without blocking the HTTP web request.
    """
    app = current_app._get_current_object()
    thread = threading.Thread(target=_async_send_email_task, args=(app, to_email, otp_code, user_name))
    thread.daemon = True
    thread.start()
    return True


def register_organisation(form_data):
    """
    Atomically registers a new Company, its Company Admin User, and its Wallet inside
    a single database transaction. Sends real OTP email upon success.
    Returns (user, company, otp_code) on success.
    """
    try:
        company = Company(
            name=form_data['company_name'].strip(),
            authorised_signatory_name=form_data['authorised_signatory_name'].strip(),
            email=form_data['email'].strip().lower(),
            phone=form_data['phone'].strip(),
            country=form_data.get('country', 'India').strip(),
            state=form_data['state'].strip(),
            city=form_data['city'].strip(),
            zip_code=form_data['zip_code'].strip(),
            gstin=form_data.get('gstin', '').strip().upper() if form_data.get('gstin') else None,
            address=form_data['address'].strip(),
            status='pending_verification'
        )
        db.session.add(company)
        db.session.flush()

        otp_code = generate_otp()
        otp_expires = datetime.now(timezone.utc) + timedelta(minutes=15)

        user = User(
            company_id=company.id,
            name=form_data['authorised_signatory_name'].strip(),
            email=form_data['email'].strip().lower(),
            phone=form_data['phone'].strip(),
            role='company_admin',
            email_verified=False,
            otp_code=otp_code,
            otp_expires_at=otp_expires,
            status='active'
        )
        user.set_password(form_data['password'])
        db.session.add(user)

        wallet = Wallet(
            company_id=company.id,
            balance=Decimal('0.00'),
            currency='INR',
            status='active'
        )
        db.session.add(wallet)

        db.session.commit()

        # Send Real SMTP Email asynchronously
        send_real_otp_email(user.email, otp_code, user.name)

        return user, company, otp_code

    except Exception as e:
        db.session.rollback()
        raise e


def verify_user_otp(user_id, entered_otp):
    """
    Verifies user OTP and marks email as verified upon match.
    Returns (success, message).
    """
    user = User.query.get(user_id)
    if not user:
        return False, "User not found."

    if user.email_verified:
        return True, "Email is already verified."

    # Allow temporary dev OTP '123456' OR actual generated OTP code
    if entered_otp.strip() != "123456" and (not user.otp_code or user.otp_code != entered_otp.strip()):
        return False, "Invalid OTP code. Please check your email inbox for the 6-digit code."

    if user.otp_expires_at:
        now = datetime.now(timezone.utc)
        expires_at = user.otp_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return False, "OTP code has expired. Please click Resend OTP Code."

    user.email_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    db.session.commit()
    return True, "Email successfully verified!"
