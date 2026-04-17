from flask import Blueprint, render_template, jsonify, session
from models import db, Account, Trade, StrategyLog
from routes.auth import login_required, current_user
from strategies import STRATEGY_LABELS

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    user = current_user()
    accounts = Account.query.filter_by(user_id=user.id).all()
    return render_template('dashboard.html', user=user, accounts=accounts, strategy_labels=STRATEGY_LABELS)


@dashboard_bp.route('/account/<int:account_id>')
@login_required
def account_detail(account_id):
    user = current_user()
    account = Account.query.get_or_404(account_id)
    if account.user_id != user.id:
        return 'Forbidden', 403
    return render_template('account.html', user=user, account=account, strategy_labels=STRATEGY_LABELS)


@dashboard_bp.route('/api/dashboard/summary')
@login_required
def summary():
    user = current_user()
    accounts = Account.query.filter_by(user_id=user.id).all()

    result = []
    for acc in accounts:
        recent_trades = acc.trades.order_by(db.text('executed_at DESC')).limit(5).all()
        result.append({
            'account': acc.to_dict(),
            'recent_trades': [t.to_dict() for t in recent_trades],
        })
    return jsonify(result)


@dashboard_bp.route('/api/dashboard/chart/<int:account_id>')
@login_required
def chart_data(account_id):
    user = current_user()
    account = Account.query.get_or_404(account_id)
    if account.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    trades = account.trades.order_by(db.text('executed_at ASC')).all()

    # 전략별 누적 손익 계산
    pnl_data = {}
    running = {}
    labels = []

    for t in trades:
        date_str = t.executed_at.strftime('%Y-%m-%d') if t.executed_at else 'unknown'
        if date_str not in labels:
            labels.append(date_str)

        strategy = t.strategy or 'unknown'
        if strategy not in pnl_data:
            pnl_data[strategy] = []
            running[strategy] = 0.0

        if t.side == 'SELL' and t.status == 'FILLED':
            running[strategy] += t.amount or 0
        elif t.side == 'BUY' and t.status == 'FILLED':
            running[strategy] -= t.amount or 0

        pnl_data[strategy].append(round(running[strategy], 2))

    return jsonify({'labels': labels, 'datasets': pnl_data})
