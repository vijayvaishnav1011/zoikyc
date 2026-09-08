from flask import Blueprint

pan_bp = Blueprint('pan', __name__, template_folder='../templates')

from app.pan import routes
