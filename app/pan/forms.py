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
        validators=[DataRequired(message="Date of Birth is required.")],
        render_kw={"type": "hidden", "id": "hiddenDobInput"}
    )
    dob_day = StringField('Day', validators=[DataRequired(message="Day is required.")])
    dob_month = StringField('Month', validators=[DataRequired(message="Month is required.")])
    dob_year = StringField('Year', validators=[DataRequired(message="Year is required.")])
    submit = SubmitField('Verify PAN Details')

