from flask import Blueprint

esign_bp = Blueprint('esign', __name__)

from app.esign.capricorn import CapricornESignProvider
from app.esign import routes

__all__ = ['esign_bp', 'CapricornESignProvider']
