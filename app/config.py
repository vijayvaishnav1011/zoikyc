import os
from dotenv import load_dotenv

load_dotenv()

# Format DATABASE_URL automatically for psycopg3 compatibility
db_url = os.environ.get('DATABASE_URL', 'postgresql+psycopg://localhost/zoikyc')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif db_url.startswith('postgresql://') and not db_url.startswith('postgresql+psycopg://'):
    db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'zoikyc-super-secret-production-key-2026!')
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # CSRF Security Settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600 # 1 hour
    
    # Razorpay Payment Gateway Credentials
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    
    # Session Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    DEBUG = False

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
