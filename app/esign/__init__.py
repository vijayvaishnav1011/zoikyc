from flask import Blueprint

esign_bp = Blueprint('esign', __name__)

from app.esign import routes  # noqa: E402,F401

__all__ = ['esign_bp']
