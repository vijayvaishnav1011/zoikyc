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
        signatory = uploadpdf['signatories']['signatory']
        self.assertEqual(signatory['name'], "Rahul Sharma")
        self.assertEqual(signatory['mode'], "online-aadhaar-otp")
        self.assertEqual(signatory['email'], "rahul@example.com")
        self.assertEqual(signatory['mail'], "y")
        self.assertEqual(signatory['mobile'], "9876543210")
        self.assertEqual(signatory['sms'], "y")
        self.assertEqual(signatory['option']['pagenum'], "all")
        self.assertEqual(signatory['option']['cood'], "400,700,550,750")

    @patch('app.integrations.capricorn.requests.post')
    def test_client_document_upload_and_dispatch(self, mock_post):
        """Test client portal document upload directly dispatches to Capricorn without debiting yet."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "command": "esign",
                "success": "OK",
                "responsedata": {
                    "items": {
                        "item": {
                            "redirecturl": "https://demo.esign.network/api/esign/v1.0/11112222/REF111/signatory1",
                            "reference": "REF111",
                            "signedpdfurl": "https://demo.esign.network/apij/getdoc/v1.0/11112222/REF111",
                            "txn": "11112222"
                        }
                    }
                }
            }
        }
        mock_post.return_value = mock_response

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
                'page_num': '1',
                'coordinates': '200,250,400,500'
            }, content_type='multipart/form-data', follow_redirects=True)

            self.assertEqual(resp.status_code, 200)

            # Assert document exists in DB and is dispatched to Capricorn
            doc = ESignDocument.query.filter_by(title='Consulting Agreement 2026').first()
            self.assertIsNotNone(doc)
            self.assertEqual(doc.status, 'sent_to_capricorn')
            self.assertEqual(doc.company_id, self.company.id)
            self.assertEqual(doc.signatory_name, 'Amit Kumar')
            self.assertEqual(doc.signatory_mobile, '9999999999')
            # Wallet float should NOT be debited on upload/dispatch
            self.assertEqual(self.wallet.balance, Decimal("500.00"))

    @patch('app.integrations.capricorn.requests.post')
    def test_admin_dispatch_and_delayed_debit(self, mock_post):
        """Test Super Admin dispatching to Capricorn: converts to Base64 without immediate debit."""
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
            self.assertEqual(updated_doc.redirect_url, 'https://demo.esign.network/api/esign/v1.0/88889999/REF888/signatory1')

            # Verify client wallet was NOT debited yet (delayed until customer completes sign)
            updated_wallet = Wallet.query.get(self.wallet.id)
            self.assertEqual(updated_wallet.balance, initial_balance)

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
    def test_capricorn_callback_and_wallet_deduction(self, mock_get):
        """Verify callback marks document as signed, downloads PDF, and dynamically debits company per_kyc_price."""
        mock_pdf_resp = MagicMock()
        mock_pdf_resp.status_code = 200
        mock_pdf_resp.content = b"%PDF-1.4 SIGNED DOCUMENT BY CAPRICORN DSC %EOF"
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

        initial_balance = self.wallet.balance  # 500.00
        expected_fee = self.company.per_kyc_price  # 25.00

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
        self.assertEqual(updated_doc.cost_charged, expected_fee)

        # Verify wallet debited by exact company.per_kyc_price
        updated_wallet = Wallet.query.get(self.wallet.id)
        self.assertEqual(updated_wallet.balance, initial_balance - expected_fee)

        # Verify WalletTransaction entry
        txn = WalletTransaction.query.filter_by(company_id=self.company.id, type='debit').first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, expected_fee)

    def test_dynamic_per_company_pricing_deduction(self):
        """Verify that two different companies with distinct per_kyc_price are debited dynamically."""
        from app.esign.routes import charge_wallet_for_signed_doc

        # Company 1: Alpha Corp has per_kyc_price = 25.00
        doc1 = ESignDocument(
            company_id=self.company.id,
            title="Agreement Corp 1",
            original_filename="sample1.pdf",
            file_path="uploads/test_sample.pdf",
            signatory_name="Client One",
            status="sent_to_capricorn",
            capricorn_txn="TXN-COMP-1"
        )
        db.session.add(doc1)

        # Company 2: Custom per_kyc_price = 45.50
        comp2 = Company(
            name="Zeta Logistics",
            authorised_signatory_name="Zeta Officer",
            email="finance@zetalogistics.in",
            phone="9988776655",
            country="India",
            state="Karnataka",
            city="Bengaluru",
            zip_code="560001",
            address="Koramangala, Bengaluru",
            status="active",
            per_kyc_price=Decimal("45.50"),
            min_recharge_amount=Decimal("1000.00")
        )
        db.session.add(comp2)
        db.session.flush()

        wallet2 = Wallet(company_id=comp2.id, balance=Decimal("100.00"))
        db.session.add(wallet2)

        doc2 = ESignDocument(
            company_id=comp2.id,
            title="Agreement Zeta Logistics",
            original_filename="sample2.pdf",
            file_path="uploads/test_sample.pdf",
            signatory_name="Client Two",
            status="sent_to_capricorn",
            capricorn_txn="TXN-COMP-2"
        )
        db.session.add(doc2)
        db.session.commit()

        # Execute charge for doc 1
        charged1 = charge_wallet_for_signed_doc(doc1)
        self.assertTrue(charged1)
        self.assertEqual(doc1.cost_charged, Decimal("25.00"))
        self.assertEqual(Wallet.query.get(self.wallet.id).balance, Decimal("500.00") - Decimal("25.00"))

        # Execute charge for doc 2
        charged2 = charge_wallet_for_signed_doc(doc2)
        self.assertTrue(charged2)
        self.assertEqual(doc2.cost_charged, Decimal("45.50"))
        self.assertEqual(Wallet.query.get(wallet2.id).balance, Decimal("100.00") - Decimal("45.50"))

        # Verify idempotency: charging doc 1 again returns False and balance remains unchanged
        charged1_again = charge_wallet_for_signed_doc(doc1)
        self.assertFalse(charged1_again)
        self.assertEqual(Wallet.query.get(self.wallet.id).balance, Decimal("475.00"))

    def test_admin_esign_requests_company_grouped(self):
        """Verify that /admin/esign organizes document execution requests grouped company-wise."""
        # Create second company Beta Corp
        beta_comp = Company(
            name="Beta Innovations",
            authorised_signatory_name="Beta Director",
            email="contact@betainno.com",
            phone="9123456780",
            country="India",
            state="Maharashtra",
            city="Mumbai",
            zip_code="400001",
            address="Nariman Point, Mumbai",
            status="active"
        )
        db.session.add(beta_comp)
        db.session.flush()

        beta_wallet = Wallet(company_id=beta_comp.id, balance=Decimal("200.00"))
        db.session.add(beta_wallet)
        db.session.commit()

        # Add documents to both companies
        doc1 = ESignDocument(
            company_id=self.company.id,
            title="Alpha Partnership Agreement",
            signatory_name="Pankaj Signer",
            original_filename="alpha.pdf",
            file_path="uploads/test_sample.pdf",
            status="pending_admin"
        )
        doc2 = ESignDocument(
            company_id=beta_comp.id,
            title="Beta Vendor Contract",
            signatory_name="Beta Signer",
            original_filename="beta.pdf",
            file_path="uploads/test_sample.pdf",
            status="pending_admin"
        )
        db.session.add_all([doc1, doc2])
        db.session.commit()

        # Log in as super admin
        super_admin = User.query.filter_by(role='super_admin').first()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(super_admin.id)

        # GET /admin/esign-requests
        resp = self.client.get('/admin/esign-requests')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')

        # Check both companies and documents appear
        self.assertIn("Alpha Corp", html)
        self.assertIn("Alpha Partnership Agreement", html)
        self.assertIn("Beta Innovations", html)
        self.assertIn("Beta Vendor Contract", html)

        # Test filtering by Alpha Corp only
        filter_resp = self.client.get(f'/admin/esign-requests?company_id={self.company.id}')
        self.assertEqual(filter_resp.status_code, 200)
        filter_html = filter_resp.data.decode('utf-8')
        self.assertIn("Alpha Partnership Agreement", filter_html)
        self.assertNotIn("Beta Vendor Contract", filter_html)

if __name__ == '__main__':
    unittest.main()
