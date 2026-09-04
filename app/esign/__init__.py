from flask import Blueprint

esign_bp = Blueprint('esign', __name__)

from app.esign import routes
