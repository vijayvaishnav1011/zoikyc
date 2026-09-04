from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

class ESignUploadForm(FlaskForm):
    title = StringField('Document Title / Agreement Name *', validators=[
        DataRequired(message='Document title is required.'),
        Length(min=1, max=150, message='Document title must be between 1 and 150 characters.')
    ], render_kw={"placeholder": "e.g. Master Service Agreement, Offer Letter, NDA"})

    pdf_file = FileField('Select PDF Document (Max 15MB) *', validators=[
        FileRequired(message='Please select a PDF document file to upload.'),
        FileAllowed(['pdf', 'PDF'], 'Only PDF documents (.pdf) are supported for Aadhaar E-Sign.')
    ])

    signatory_name = StringField('Customer / Signatory Name (As on Aadhaar) *', validators=[
        DataRequired(message='Customer full name (as on Aadhaar) is required.'),
        Length(min=1, max=120, message='Name must be between 1 and 120 characters.')
    ], render_kw={"placeholder": "e.g. Rahul Sharma"})

    signatory_mobile = StringField('Customer Mobile', validators=[
        Optional(),
        Length(max=20)
    ])

    signatory_email = StringField('Customer Email', validators=[
        Optional(),
        Length(max=120)
    ])

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
