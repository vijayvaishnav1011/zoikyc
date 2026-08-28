from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.auth.forms import RegistrationForm, OTPVerificationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from app.auth.services import register_organisation, verify_user_otp, generate_otp, send_real_otp_email
from app.models.user import User
from app.extensions import db
from datetime import datetime, timedelta, timezone

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user, company, otp_code = register_organisation(form.data)
            session['pending_user_id'] = user.id
            print(f"\n=======================================================")
            print(f"📧 [SMTP MOCK EMAIL SENDER] Sent OTP: {otp_code} to {user.email}")
            print(f"=======================================================\n")
            flash(f"Verification OTP code sent to {user.email}. Please check your inbox.", "info")
            return redirect(url_for('auth.verify_otp'))
        except Exception as e:
            flash(f"Registration error: {str(e)}", "danger")

    return render_template('auth/register.html', form=form)

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    pending_user_id = session.get('pending_user_id')
    if not pending_user_id:
        flash("No registration session found. Please register first.", "warning")
        return redirect(url_for('auth.register'))

    user = User.query.get(pending_user_id)
    if not user:
        flash("Invalid registration session.", "danger")
        return redirect(url_for('auth.register'))

    form = OTPVerificationForm()
    if form.validate_on_submit():
        success, message = verify_user_otp(user.id, form.otp.data)
        if success:
            session.pop('pending_user_id', None)
            login_user(user)
            flash("Welcome to ZoiKYC! Your account has been verified.", "success")
            return redirect(url_for('dashboard.index'))
        else:
            flash(message, "danger")

    return render_template('auth/verify_otp.html', form=form, user=user)

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    pending_user_id = session.get('pending_user_id')
    if not pending_user_id:
        flash("No active verification session.", "warning")
        return redirect(url_for('auth.register'))

    user = User.query.get(pending_user_id)
    if user:
        new_otp = generate_otp()
        user.otp_code = new_otp
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.session.commit()

        # Send Real SMTP Email
        send_real_otp_email(user.email, new_otp, user.name)

        flash(f"A new OTP verification code has been sent to {user.email}.", "info")
    return redirect(url_for('auth.verify_otp'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            if not user.email_verified:
                session['pending_user_id'] = user.id
                new_otp = generate_otp()
                user.otp_code = new_otp
                user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
                db.session.commit()

                # Send Real SMTP Email
                send_real_otp_email(user.email, new_otp, user.name)

                flash(f"Please verify your email address to continue. An OTP code has been sent to {user.email}.", "warning")
                return redirect(url_for('auth.verify_otp'))

            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash("Logged in successfully.", "success")
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash("Invalid email or password.", "danger")

    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            flash(f"Password reset instructions sent to {user.email} (Demo reset code: 123456)", "info")
        else:
            flash("If that email address exists in our database, password reset instructions have been sent.", "info")
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)
