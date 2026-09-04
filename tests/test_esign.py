import os
import io
import json
import base64
import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.models.esign import ESignDocument
from app.integrations.capricorn import CapricornESignProvider

class ESignIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create dummy PDF file for tests
        self.test_pdf_path = os.path.join(self.app.root_path, 'uploads', 'test_sample.pdf')
        os.makedirs(os.path.dirname(self.test_pdf_path), exist_ok=True)
        with open(self.test_pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4 Mock PDF Content for ZoiKYC Unit Testing %EOF")

        # Create Test Client Company
        self.company = Company(
            name="Alpha Corp",
            authorised_signatory_name="Pankaj Vaishnav",
            email="contact@alphacorp.com",
            phone="9876543210",
            country="India",
            state="Delhi",
            city="New Delhi",
            zip_code="110001",
            address="Connaught Place, New Delhi",
            status="active",
            per_kyc_price=Decimal("25.00"),
            min_recharge_amount=Decimal("1000.00")
        )
        db.session.add(self.company)
        db.session.commit()

        # Create Client Wallet with float
        self.wallet = Wallet(
            company_id=self.company.id,
            balance=Decimal("500.00")
        )
        db.session.add(self.wallet)

        # Create Client User
        self.user = User(
            name="Pankaj Vaishnav",
            email="user@alphacorp.com",
            phone="9876543210",
            role="company_admin",
            company_id=self.company.id,
            email_verified=True,
            status="active"
        )
        self.user.set_password("SecurePass123!")
        db.session.add(self.user)

        # Retrieve Super Admin user seeded by create_app
        self.admin = User.query.filter_by(email="info@zoikyc.com").first()
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        if os.path.exists(self.test_pdf_path):
            os.remove(self.test_pdf_path)

    def test_capricorn_pdf_to_base64_conversion(self):
        """Verify that CapricornESignProvider correctly reads and encodes PDF files to Base64."""
        provider = CapricornESignProvider()
        b64_str = provider.convert_pdf_to_base64(self.test_pdf_path)
        decoded = base64.b64decode(b64_str)
        self.assertIn(b"%PDF-1.4", decoded)

    @patch('requests.post')
    def test_capricorn_send_document_payload_structure(self, mock_post):
        """Verify the exact JSON structure sent to Capricorn matches specification."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "command": "esign",
                "success": "OK",
                "responsedata": {
                    "items": {
                        "item": {
                            "redirecturl": "https://demo.esign.network/api/esign/v1.0/12345678/REF123/signatory1",
                            "reference": "REF123",
                            "signedpdfurl": "https://demo.esign.network/apij/getdoc/v1.0/12345678/REF123",
                            "txn": "12345678"
                        }
                    }
                }
            }
        }
        mock_post.return_value = mock_response

        provider = CapricornESignProvider()
        res = provider.send_document_for_esign(
            doc_title="Service Agreement",
            pdf_file_path=self.test_pdf_path,
            signatory_name="Rahul Sharma",
            signatory_mobile="9876543210",
            signatory_email="rahul@example.com",
            callback_url="https://zoikyc.com/esign/callback"
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['txn'], "12345678")
        self.assertEqual(res['reference'], "REF123")
        self.assertIn("signatory1", res['redirect_url'])

        # Verify call arguments
        sent_json = mock_post.call_args[1]['json']
        self.assertEqual(sent_json['request']['auth']['command'], 'esign')
        self.assertEqual(sent_json['request']['auth']['token'], provider.DEFAULT_TOKEN)
        uploadpdf = sent_json['request']['parameter']['uploadpdf']
        self.assertTrue(len(uploadpdf['pdf64']) > 0)
        self.assertEqual(uploadpdf['title'], "Service Agreement")
        signatory = uploadpdf['signatories']['signatory'][0]
        self.assertEqual(signatory['name'], "Rahul Sharma")
        self.assertEqual(signatory['mode'], "online-aadhaar-otp")
        self.assertEqual(signatory['email'], "na@zoikyc.com")
        self.assertEqual(signatory['mail'], "n")
        self.assertEqual(signatory['mobile'], "9999999999")
        self.assertEqual(signatory['sms'], "n")

    def test_client_document_upload(self):
        """Test client portal document upload creating a pending_admin document."""
        with self.client:
            # Login as client user
            self.client.post('/login', data={
                'email': 'user@alphacorp.com',
                'password': 'SecurePass123!'
            }, follow_redirects=True)

            pdf_data = (io.BytesIO(b"%PDF-1.4 test document content %EOF"), 'agreement.pdf')
            resp = self.client.post('/esign/upload', data={
                'title': 'Consulting Agreement 2026',
                'pdf_file': pdf_data,
                'signatory_name': 'Amit Kumar',
                'signatory_mobile': '9876543210',
                'signatory_email': 'amit@alphacorp.com',
                'page_num': '1',
                'coordinates': '200,250,400,500'
            }, content_type='multipart/form-data', follow_redirects=True)

            self.assertEqual(resp.status_code, 200)

            # Assert document exists in DB
            doc = ESignDocument.query.filter_by(title='Consulting Agreement 2026').first()
            self.assertIsNotNone(doc)
            self.assertEqual(doc.status, 'pending_admin')
            self.assertEqual(doc.company_id, self.company.id)
            self.assertEqual(doc.signatory_name, 'Amit Kumar')

    @patch('app.integrations.capricorn.requests.post')
    def test_admin_dispatch_and_wallet_deduction(self, mock_post):
        """Test Super Admin dispatching to Capricorn: converts to Base64, debits wallet float."""
        # Mock Capricorn response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "command": "esign",
                "success": "OK",
                "responsedata": {
                    "items": {
                        "item": {
                            "redirecturl": "https://demo.esign.network/api/esign/v1.0/88889999/REF888/signatory1",
                            "reference": "REF888",
                            "signedpdfurl": "https://demo.esign.network/apij/getdoc/v1.0/88889999/REF888",
                            "txn": "88889999"
                        }
                    }
                }
            }
        }
        mock_post.return_value = mock_response

        # Create pending document
        doc = ESignDocument(
            company_id=self.company.id,
            title="Vendor Contract",
            original_filename="contract.pdf",
            file_path="uploads/test_sample.pdf",
            signatory_name="Sunil Verma",
            signatory_mobile="9812345678",
            sign_mode="online-aadhaar-otp",
            status="pending_admin"
        )
        db.session.add(doc)
        db.session.commit()

        initial_balance = self.wallet.balance  # 500.00
        per_sign_fee = self.company.per_kyc_price  # 25.00

        with self.client:
            # Login as Super Admin
            self.client.post('/login', data={
                'email': 'info@zoikyc.com',
                'password': 'Admin@32132321'
            }, follow_redirects=True)

            # Dispatch document
            resp = self.client.post(f'/admin/esign/{doc.id}/dispatch', follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            # Verify document updated
            updated_doc = ESignDocument.query.get(doc.id)
            self.assertEqual(updated_doc.status, 'sent_to_capricorn')
            self.assertEqual(updated_doc.capricorn_txn, '88889999')
            self.assertEqual(updated_doc.capricorn_reference, 'REF888')
            self.assertEqual(updated_doc.redirect_url, 'https://demo.esign.digital/api/esign/v1.0/88889999/REF888/signatory1')

            # Verify client wallet was debited by per_kyc_price (25.00)
            updated_wallet = Wallet.query.get(self.wallet.id)
            self.assertEqual(updated_wallet.balance, initial_balance - per_sign_fee)

            # Verify WalletTransaction entry was created
            txn = WalletTransaction.query.filter_by(company_id=self.company.id, type='debit').first()
            self.assertIsNotNone(txn)
            self.assertEqual(txn.amount, per_sign_fee)
            self.assertIn("Aadhaar E-Sign charge", txn.description)

    def test_admin_dispatch_blocked_on_insufficient_balance(self):
        """Verify Super Admin cannot dispatch if client has insufficient float."""
        # Set wallet balance to 0
        self.wallet.balance = Decimal("0.00")
        db.session.commit()

        doc = ESignDocument(
            company_id=self.company.id,
            title="Insufficient Float Doc",
            original_filename="sample.pdf",
            file_path="uploads/test_sample.pdf",
            signatory_name="Test Signer",
            signatory_mobile="9812345678",
            status="pending_admin"
        )
        db.session.add(doc)
        db.session.commit()

        with self.client:
            self.client.post('/login', data={
                'email': 'info@zoikyc.com',
                'password': 'Admin@32132321'
            }, follow_redirects=True)

            resp = self.client.post(f'/admin/esign/{doc.id}/dispatch', follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            # Document must remain pending_admin
            updated_doc = ESignDocument.query.get(doc.id)
            self.assertEqual(updated_doc.status, 'pending_admin')

    @patch('app.integrations.capricorn.requests.get')
    def test_capricorn_callback_and_signed_download(self, mock_get):
        """Verify callback marks document as signed and downloads finalized PDF."""
        # Mock Capricorn GET request for signed PDF
        mock_pdf_resp = MagicMock()
        mock_pdf_resp.status_code = 200
        mock_pdf_resp.iter_content.return_value = [b"%PDF-1.4 SIGNED DOCUMENT BY CAPRICORN DSC %EOF"]
        mock_get.return_value = mock_pdf_resp

        doc = ESignDocument(
            company_id=self.company.id,
            title="Signed NDA",
            original_filename="nda.pdf",
            file_path="uploads/test_sample.pdf",
            signatory_name="Vikram Singh",
            signatory_mobile="9876543210",
            status="sent_to_capricorn",
            capricorn_txn="99991111",
            capricorn_reference="REF9999",
            signed_pdf_url="https://demo.esign.network/apij/getdoc/v1.0/99991111/REF9999"
        )
        db.session.add(doc)
        db.session.commit()

        # Simulate Capricorn redirect callback
        resp = self.client.get(
            f'/esign/callback?txn=99991111&reference=REF9999&status=SUCCESS',
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        # Verify state
        updated_doc = ESignDocument.query.get(doc.id)
        self.assertEqual(updated_doc.status, 'signed')
        self.assertIsNotNone(updated_doc.signed_at)
        self.assertIsNotNone(updated_doc.signed_file_path)

if __name__ == '__main__':
    unittest.main()
