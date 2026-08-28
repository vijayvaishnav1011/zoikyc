from decimal import Decimal
from app import create_app
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.auth.services import register_organisation, verify_user_otp
from app.wallet.services import process_wallet_recharge

app = create_app('development')

def test_full_pipeline():
    with app.app_context():
        print("🔍 Testing Multi-Tenant Pipeline & Definition of Done...")

        # 1. Register Organisation
        form_data = {
            'company_name': 'Alpha Investments',
            'authorised_signatory_name': 'Rohan Mehta',
            'email': 'rohan@alphainvest.com',
            'phone': '+91 9988776655',
            'country': 'India',
            'state': 'Delhi',
            'city': 'New Delhi',
            'zip_code': '110001',
            'gstin': '07AAAAA1234A1Z2',
            'address': 'Connaught Place, New Delhi',
            'password': 'AlphaPassword123!'
        }

        user, company, otp_code = register_organisation(form_data)
        print(f"✅ Created Company: {company.name} (ID: {company.id})")
        print(f"✅ Created User: {user.email} (Email Verified: {user.email_verified})")
        print(f"✅ Created Wallet Balance: ₹{company.wallet.balance}")

        # 2. Verify OTP
        success, msg = verify_user_otp(user.id, otp_code)
        assert success is True
        print(f"✅ Verified OTP successfully. User status: Email Verified={user.email_verified}")

        # 3. Recharge Wallet
        recharge_ok, txn, msg = process_wallet_recharge(company.id, Decimal('10000.00'), 'upi')
        assert recharge_ok is True
        assert txn.amount == Decimal('10000.00')
        print(f"✅ Wallet Recharged: +₹{txn.amount:,.2f} | New Balance: ₹{company.wallet.balance:,.2f} | Ref: {txn.reference_id}")

        # 4. Verify Tenant Isolation
        tradeura = Company.query.filter_by(email="admin@tradeura.com").first()
        elite = Company.query.filter_by(email="admin@elitefinserv.com").first()
        
        tradeura_txns = WalletTransaction.query.filter_by(company_id=tradeura.id).all()
        elite_txns = WalletTransaction.query.filter_by(company_id=elite.id).all()
        alpha_txns = WalletTransaction.query.filter_by(company_id=company.id).all()

        print(f"🔒 Tenant Isolation Check:")
        print(f"   Tradeura Balance: ₹{tradeura.wallet.balance:,.2f} (Txn Count: {len(tradeura_txns)})")
        print(f"   Elite Finserv Balance: ₹{elite.wallet.balance:,.2f} (Txn Count: {len(elite_txns)})")
        print(f"   Alpha Investments Balance: ₹{company.wallet.balance:,.2f} (Txn Count: {len(alpha_txns)})")

        assert tradeura.wallet.balance == Decimal('25000.00')
        assert elite.wallet.balance == Decimal('5000.00')
        assert company.wallet.balance == Decimal('10000.00')

        print("🎉 ALL CHECKS PASSED PERFECTLY!")

if __name__ == '__main__':
    test_full_pipeline()
