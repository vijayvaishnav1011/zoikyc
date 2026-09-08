from flask import Blueprint

wallet_bp = Blueprint('wallet', __name__)

from app.wallet import routes
from app.wallet import cli  # noqa: F401 — registers CLI commands (flask wallet reconcile-pending)
