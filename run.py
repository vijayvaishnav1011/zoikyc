import os
from app import create_app
from app.extensions import db
from app.models import Company, User, Wallet, WalletTransaction

app = create_app(os.environ.get('FLASK_ENV', 'development'))

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'Company': Company,
        'User': User,
        'Wallet': Wallet,
        'WalletTransaction': WalletTransaction
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    use_reloader = os.environ.get('FLASK_USE_RELOADER', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=use_reloader)
