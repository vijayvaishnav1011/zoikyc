from flask_wtf import FlaskForm
from wtforms import DecimalField, StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange

class RechargeWalletForm(FlaskForm):
    amount = DecimalField('Recharge Amount (₹)', validators=[
        DataRequired(message='Please enter a valid amount.'),
        NumberRange(min=1, max=10000000, message='Amount must be between ₹1 and ₹1,00,00,000.')
    ], places=2)
    payment_method = SelectField('Payment Method', choices=[
        ('upi', 'UPI / NetBanking (Instant)'),
        ('card', 'Credit / Debit Card'),
        ('bank_transfer', 'NEFT / RTGS Bank Transfer')
    ], default='upi')
    submit = SubmitField('Proceed to Payment')
