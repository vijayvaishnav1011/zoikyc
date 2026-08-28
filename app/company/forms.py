from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length

class CompanyProfileForm(FlaskForm):
    company_name = StringField('Company / Organisation Name', validators=[
        DataRequired(), Length(max=150)
    ])
    authorised_signatory_name = StringField('Authorised Signatory Name', validators=[
        DataRequired(), Length(max=150)
    ])
    phone = StringField('Business Phone', validators=[
        DataRequired(), Length(max=20)
    ])
    gstin = StringField('GSTIN', validators=[
        Length(max=20)
    ])
    country = StringField('Country', validators=[
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
    address = TextAreaField('Registered Address', validators=[
        DataRequired()
    ])
    submit = SubmitField('Save Profile Changes')


class CompanyDocumentUploadForm(FlaskForm):
    document_type = SelectField('Document Type *', choices=[
        ('certificate_of_incorporation', '1. Certificate of Incorporation / Registration Certificate'),
        ('company_pan', '2. Company PAN Card Document'),
        ('gst_certificate', '3. GSTIN Registration Certificate'),
        ('board_resolution', '4. Authorised Signatory Board Resolution / ID Proof'),
        ('bank_proof', '5. Bank Account Proof (Cancelled Cheque / Statement)')
    ], validators=[DataRequired()])

    document_file = FileField('Upload Document File (PDF, PNG, JPG, DOCX) *', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg', 'docx', 'doc'], 'Only PDF, Image, or Word (DOCX) files are allowed.')
    ])

    notes = TextAreaField('Additional Notes / Document Details (Optional)')
    submit = SubmitField('Upload Document for Verification')
