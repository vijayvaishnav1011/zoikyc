from decimal import Decimal
from app import create_app
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.wallet.services import get_razorpay_client, create_razorpay_order

app = create_app('development')

def test_razorpay_integration():
    with app.app_context():
        print("🔍 Testing Razorpay Payment Gateway Integration...")

        client = get_razorpay_client()
        key_id = app.config.get('RAZORPAY_KEY_ID')
        print(f"💳 Configured Key ID: {key_id}")

        if client:
            print("✅ Razorpay Client successfully initialized with credentials!")
            test_company = Company.query.first()
            if test_company:
                order, err = create_razorpay_order(100.00, test_company.id, test_company.name)
                if order:
                    print(f"✅ Real Razorpay Order Created: ID={order['id']}, Amount={order['amount']} paise, Currency={order['currency']}")
                else:
                    print(f"ℹ️ Order Creation note (e.g. Test Key): {err}")
        else:
            print("ℹ️ Razorpay keys not yet loaded or client returned None.")

if __name__ == '__main__':
    test_razorpay_integration()
