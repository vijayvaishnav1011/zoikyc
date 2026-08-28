from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login_manager

try:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='company_admin') # super_admin, company_admin
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    otp_code = db.Column(db.String(10), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default='active') # active, inactive
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        if HAS_ARGON2:
            self.password_hash = ph.hash(password)
        else:
            self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        if HAS_ARGON2 and self.password_hash.startswith('$argon2'):
            try:
                return ph.verify(self.password_hash, password)
            except Exception:
                return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} (Company ID: {self.company_id})>"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
