from flask import Blueprint, render_template

strategies_bp = Blueprint('strategies', __name__)


@strategies_bp.route('/strategies')
def strategies():
    return render_template('strategies.html')
