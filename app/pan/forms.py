import re
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, Optional

class PANCheckForm(FlaskForm):
    pan_number = StringField(
        'PAN Card Number',
        validators=[
            DataRequired(message="PAN number is required."),
            Length(min=10, max=10, message="PAN number must be exactly 10 characters."),
            Regexp(r'^[A-Za-z]{5}[0-9]{4}[A-Za-z]{1}$', message="Invalid PAN format (e.g. ABCDE1234F).")
        ],
        render_kw={
            "placeholder": "e.g. ABCDE1234F",
            "maxlength": "10",
            "style": "text-transform: uppercase; font-family: monospace; font-size: 1.05rem; letter-spacing: 1px;"
        }
    )
    dob = StringField(
        'Date of Birth',
        validators=[Optional()],
        render_kw={
            "placeholder": "DD/MM/YYYY (Optional)",
            "autocomplete": "off",
            "class": "form-control custom-date-picker"
        }
    )
    submit = SubmitField('Verify PAN Details')
