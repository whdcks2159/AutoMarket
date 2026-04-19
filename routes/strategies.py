from flask import Blueprint, render_template, session
from models import User

strategies_bp = Blueprint('strategies', __name__)


@strategies_bp.route('/strategies')
def strategies():
    user = User.query.get(session['user_id']) if 'user_id' in session else None
    return render_template('strategies.html', user=user)
