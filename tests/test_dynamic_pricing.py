import unittest
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models.company import Company
from app.models.wallet import Wallet
from app.models.esign import ESignDocument
from app.models.transaction import WalletTransaction
from app.esign.routes import charge_wallet_for_signed_doc

class DynamicPricingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_dynamic_per_kyc_deduction_custom_rates(self):
        """Test that different companies have their exact custom per_kyc_price deducted upon completion."""
        # 1. Company A: Rate = ₹12.50
        company_a = Company(
            name="FinTech Solutions Pvt Ltd",
            authorised_signatory_name="Ramesh Sharma",
            email="ramesh@fintech.test",
            phone="9876543210",
            country="India",
            state="Delhi",
            city="New Delhi",
            zip_code="110001",
            address="Connaught Place, New Delhi",
            status="active",
            per_kyc_price=Decimal("12.50"),
            min_recharge_amount=Decimal("500.00")
        )
        db.session.add(company_a)
        db.session.flush()

        wallet_a = Wallet(company_id=company_a.id, balance=Decimal("200.00"))
        db.session.add(wallet_a)

        doc_a = ESignDocument(
            company_id=company_a.id,
            title="FinTech Customer Agreement",
            original_filename="fintech.pdf",
            file_path="uploads/test.pdf",
            signatory_name="Ramesh Sharma",
            status="sent_to_capricorn",
            capricorn_txn="CAP-TXN-001"
        )
        db.session.add(doc_a)

        # 2. Company B: Rate = ₹35.00
        company_b = Company(
            name="Apex Wealth Partners",
            authorised_signatory_name="Priya Patel",
            email="priya@apexwealth.test",
            phone="9123456789",
            country="India",
            state="Gujarat",
            city="Ahmedabad",
            zip_code="380001",
            address="SG Highway, Ahmedabad",
            status="active",
            per_kyc_price=Decimal("35.00"),
            min_recharge_amount=Decimal("1000.00")
        )
        db.session.add(company_b)
        db.session.flush()

        wallet_b = Wallet(company_id=company_b.id, balance=Decimal("500.00"))
        db.session.add(wallet_b)

        doc_b = ESignDocument(
            company_id=company_b.id,
            title="Wealth Advisory Mandate",
            original_filename="wealth.pdf",
            file_path="uploads/test.pdf",
            signatory_name="Priya Patel",
            status="sent_to_capricorn",
            capricorn_txn="CAP-TXN-002"
        )
        db.session.add(doc_b)
        db.session.commit()

        # Step 1: Complete signing for Company A
        res_a = charge_wallet_for_signed_doc(doc_a)
        self.assertTrue(res_a)
        
        # Verify Company A was charged exactly ₹12.50
        self.assertEqual(doc_a.cost_charged, Decimal("12.50"))
        wallet_a_refreshed = Wallet.query.get(wallet_a.id)
        self.assertEqual(wallet_a_refreshed.balance, Decimal("200.00") - Decimal("12.50")) # 187.50

        txn_a = WalletTransaction.query.filter_by(company_id=company_a.id, type='debit').first()
        self.assertIsNotNone(txn_a)
        self.assertEqual(txn_a.amount, Decimal("12.50"))
        self.assertIn("12.50", txn_a.description)

        # Step 2: Complete signing for Company B
        res_b = charge_wallet_for_signed_doc(doc_b)
        self.assertTrue(res_b)

        # Verify Company B was charged exactly ₹35.00
        self.assertEqual(doc_b.cost_charged, Decimal("35.00"))
        wallet_b_refreshed = Wallet.query.get(wallet_b.id)
        self.assertEqual(wallet_b_refreshed.balance, Decimal("500.00") - Decimal("35.00")) # 465.00

        txn_b = WalletTransaction.query.filter_by(company_id=company_b.id, type='debit').first()
        self.assertIsNotNone(txn_b)
        self.assertEqual(txn_b.amount, Decimal("35.00"))
        self.assertIn("35.00", txn_b.description)

        # Step 3: Idempotency test (charging doc_a again should do nothing)
        res_a_repeat = charge_wallet_for_signed_doc(doc_a)
        self.assertFalse(res_a_repeat)
        self.assertEqual(Wallet.query.get(wallet_a.id).balance, Decimal("187.50"))

if __name__ == '__main__':
    unittest.main()
