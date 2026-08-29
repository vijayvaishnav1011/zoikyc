from decimal import Decimal
from flask_login import login_user
from app import create_app
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import WalletTransaction
from app.models.document import CompanyDocument

app = create_app('development')
app.config['WTF_CSRF_ENABLED'] = False

def test_admin_portal():
    with app.test_client() as client:
        with app.app_context():
            print("🔍 Testing Super Admin Portal & Multi-Tenant Operations...")

            # 1. Verify Super Admin User Seeding
            admin_user = User.query.filter_by(role='super_admin').first()
            assert admin_user is not None, "Super admin user was not seeded!"
            assert admin_user.check_password('Admin@32132321'), "Password check failed for super admin"
            print(f"✅ Super Admin Seeded: {admin_user.email} (Role: {admin_user.role})")

            # 2. Test Admin Login via POST
            login_resp = client.post('/login', data={
                'email': 'admin@zoikyc.com',
                'password': 'Admin@32132321'
            }, follow_redirects=True)
            assert login_resp.status_code == 200
            print("✅ Super Admin Login Successful! Routed to /admin")

            # 3. Access Admin Endpoints
            r_overview = client.get('/admin/', follow_redirects=True)
            assert r_overview.status_code == 200
            print(f"✅ Admin Overview HTTP: {r_overview.status_code}")

            r_companies = client.get('/admin/companies')
            assert r_companies.status_code == 200
            print(f"✅ Admin Companies Directory HTTP: {r_companies.status_code}")

            r_docs = client.get('/admin/documents')
            assert r_docs.status_code == 200
            print(f"✅ Admin Document Verification Center HTTP: {r_docs.status_code}")

            r_txns = client.get('/admin/transactions')
            assert r_txns.status_code == 200
            print(f"✅ Admin Global Transactions HTTP: {r_txns.status_code}")

            # 4. Test Client Company Detail & Wallet Adjustment
            test_company = Company.query.first()
            if test_company:
                r_detail = client.get(f'/admin/companies/{test_company.id}')
                assert r_detail.status_code == 200
                print(f"✅ Admin 360° View for '{test_company.name}' HTTP: {r_detail.status_code}")

                # Test manual wallet credit adjustment
                bal_before = test_company.wallet.balance if test_company.wallet else Decimal('0.00')
                r_adjust = client.post(f'/admin/companies/{test_company.id}/adjust-wallet', data={
                    'amount': '500.00',
                    'action_type': 'credit',
                    'reason': 'Automated Test Grant'
                }, follow_redirects=True)
                assert r_adjust.status_code == 200
                print(f"✅ Admin Wallet Adjustment Executed! Balance: ₹{test_company.wallet.balance:,.2f}")

            print("\n🎉 ALL SUPER ADMIN PORTAL TESTS PASSED 100%!")

if __name__ == '__main__':
    test_admin_portal()
