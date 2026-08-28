from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
from app.models.user import User
from app.models.company import Company

class RegistrationForm(FlaskForm):
    # Organisation Details
    authorised_signatory_name = StringField('Authorised Signatory Name', validators=[
        DataRequired(), Length(max=150)
    ])
    company_name = StringField('Company / Organisation Name', validators=[
        DataRequired(), Length(max=150)
    ])
    country = StringField('Country', default='India', validators=[
        DataRequired(), Length(max=100)
    ])
    state = StringField('State', validators=[
        DataRequired(), Length(max=100)
    ])
    city = StringField('City', validators=[
        DataRequired(), Length(max=100)
    ])
    zip_code = StringField('ZIP / Postal Code', validators=[
        DataRequired(), Length(max=20)
    ])
    gstin = StringField('GSTIN', validators=[
        Length(max=20)
    ])
    address = TextAreaField('Registered Business Address', validators=[
        DataRequired()
    ])

    # Contact Details
    email = StringField('Business Email', validators=[
        DataRequired(), Email(), Length(max=150)
    ])
    phone = StringField('Mobile Number', validators=[
        DataRequired(), Length(min=10, max=20)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=8, message="Password must be at least 8 characters long.")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])

    # Agreement
    agree_terms = BooleanField('I agree to the Terms & Conditions and Privacy Policy', validators=[
        DataRequired(message='You must agree to the Terms & Conditions to register.')
    ])

    submit = SubmitField('Create Organisation Account')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('This business email is already registered. Please sign in or use another email.')
        if Company.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('A company with this email is already registered.')


class OTPVerificationForm(FlaskForm):
    otp = StringField('Enter 6-Digit OTP', validators=[
        DataRequired(), Length(min=6, max=6, message='OTP must be 6 digits.')
    ])
    submit = SubmitField('Verify Email')


class LoginForm(FlaskForm):
    email = StringField('Business Email', validators=[
        DataRequired(), Email()
    ])
    password = PasswordField('Password', validators=[
        DataRequired()
    ])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class ForgotPasswordForm(FlaskForm):
    email = StringField('Business Email', validators=[
        DataRequired(), Email()
    ])
    submit = SubmitField('Send Password Reset Link')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(), Length(min=8)
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Reset Password')
