from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

class ESignUploadForm(FlaskForm):
    title = StringField('Document Title / Agreement Name *', validators=[
        DataRequired(),
        Length(min=3, max=150)
    ], render_kw={"placeholder": "e.g. Master Service Agreement, Offer Letter, NDA"})

    pdf_file = FileField('Select PDF Document (Max 15MB) *', validators=[
        FileRequired(),
        FileAllowed(['pdf'], 'Only PDF documents are supported for Aadhaar E-Sign.')
    ])

    signatory_name = StringField('Customer / Signatory Name (As on Aadhaar) *', validators=[
        DataRequired(),
        Length(min=2, max=120)
    ], render_kw={"placeholder": "e.g. Rahul Sharma"})

    signatory_mobile = StringField('Customer Mobile (Aadhaar Linked Mobile) *', validators=[
        DataRequired(),
        Regexp(r'^[6-9]\d{9}$', message="Enter a valid 10-digit Indian mobile number")
    ], render_kw={"placeholder": "10-digit mobile number without +91"})

    signatory_email = StringField('Customer Email (Optional)', validators=[
        Optional(),
        Length(max=120)
    ], render_kw={"placeholder": "customer@example.com"})

    client_remarks = TextAreaField('Client Remarks / Purpose Notes (Optional)', validators=[
        Optional(),
        Length(max=500)
    ], render_kw={"placeholder": "e.g. Customer ID #1042, Employee onboarding KYC, Loan agreement verification", "rows": 3})

    page_num = SelectField('Signature Page Placement', choices=[
        ('1', 'Page 1 (First Page)'),
        ('all', 'All Pages'),
        ('custom', 'Custom Page')
    ], default='1')

    coordinates = StringField('Signature Box Coordinates', default='200,250,400,500', validators=[
        Optional()
    ], render_kw={"placeholder": "200,250,400,500"})

    submit = SubmitField('Upload & Create Execution Request')
