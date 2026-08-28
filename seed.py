from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models.company import Company
from app.models.user import User
from app.models.wallet import Wallet
from app.wallet.services import process_wallet_recharge

app = create_app('development')

def seed():
    with app.app_context():
        print("🌱 Seeding ZoiKYC multi-tenant database...")

        # 1. Create Tradeura Company & Admin
        tradeura_email = "admin@tradeura.com"
        company_tradeura = Company.query.filter_by(email=tradeura_email).first()
        if not company_tradeura:
            company_tradeura = Company(
                name="Tradeura Securities",
                authorised_signatory_name="Vikram Sethi",
                email=tradeura_email,
                phone="+91 9876543210",
                country="India",
                state="Maharashtra",
                city="Mumbai",
                zip_code="400001",
                gstin="27AAACT1234A1Z1",
                address="Suite 401, Trade Tower, BKC, Mumbai",
                status="active"
            )
            db.session.add(company_tradeura)
            db.session.flush()

            user_tradeura = User(
                company_id=company_tradeura.id,
                name="Vikram Sethi",
                email=tradeura_email,
                phone="+91 9876543210",
                role="company_admin",
                email_verified=True,
                status="active"
            )
            user_tradeura.set_password("Tradeura123!")
            db.session.add(user_tradeura)

            wallet_tradeura = Wallet(
                company_id=company_tradeura.id,
                balance=Decimal('0.00'),
                currency="INR",
                status="active"
            )
            db.session.add(wallet_tradeura)
            db.session.commit()

            # Process initial recharges for Tradeura
            process_wallet_recharge(company_tradeura.id, Decimal('10000.00'), 'upi', 'INIT_RECH')
            process_wallet_recharge(company_tradeura.id, Decimal('15000.00'), 'card', 'INIT_RECH')
            print("✅ Seeded Tradeura (Balance: ₹25,000.00)")
        else:
            print("ℹ️ Tradeura already exists.")

        # 2. Create Elite Finserv Company & Admin
        elite_email = "admin@elitefinserv.com"
        company_elite = Company.query.filter_by(email=elite_email).first()
        if not company_elite:
            company_elite = Company(
                name="Elite Finserv Advisory",
                authorised_signatory_name="Ananya Roy",
                email=elite_email,
                phone="+91 9820011223",
                country="India",
                state="Karnataka",
                city="Bengaluru",
                zip_code="560001",
                gstin="29AAACE5678B1Z9",
                address="7th Floor, Tech Park, Indiranagar, Bengaluru",
                status="active"
            )
            db.session.add(company_elite)
            db.session.flush()

            user_elite = User(
                company_id=company_elite.id,
                name="Ananya Roy",
                email=elite_email,
                phone="+91 9820011223",
                role="company_admin",
                email_verified=True,
                status="active"
            )
            user_elite.set_password("EliteFinserv123!")
            db.session.add(user_elite)

            wallet_elite = Wallet(
                company_id=company_elite.id,
                balance=Decimal('0.00'),
                currency="INR",
                status="active"
            )
            db.session.add(wallet_elite)
            db.session.commit()

            process_wallet_recharge(company_elite.id, Decimal('5000.00'), 'upi', 'INIT_RECH')
            print("✅ Seeded Elite Finserv (Balance: ₹5,000.00)")
        else:
            print("ℹ️ Elite Finserv already exists.")

        print("🎉 Database seeding complete!")

if __name__ == '__main__':
    seed()
