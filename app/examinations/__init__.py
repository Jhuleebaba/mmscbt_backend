from flask import Blueprint

bp = Blueprint('examinations', __name__)

from app.examinations import routes
