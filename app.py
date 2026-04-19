import os
from flask import Flask
from config import config
from models import db


def create_app(config_name: str = None) -> Flask:
    app = Flask(__name__)
    cfg_name = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[cfg_name])

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)

    with app.app_context():
        from routes.auth import auth_bp
        from routes.account import account_bp
        from routes.dashboard import dashboard_bp
        from routes.screener import screener_bp
        from routes.strategies import strategies_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(account_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(screener_bp)
        app.register_blueprint(strategies_bp)

        db.create_all()
        _migrate_schema(db)

    return app


def _migrate_schema(db):
    """기존 테이블에 누락된 컬럼을 추가한다."""
    migrations = [
        ("accounts", "screener_enabled", "BOOLEAN DEFAULT FALSE"),
        ("accounts", "screener_targets", "VARCHAR(128) DEFAULT 'KOSPI,KOSDAQ'"),
        ("accounts", "screener_max_symbols", "INTEGER DEFAULT 5"),
        ("accounts", "screener_per_symbol_limit", "FLOAT DEFAULT 500000.0"),
        ("accounts", "screener_daily_buy_limit", "INTEGER DEFAULT 3"),
    ]
    with db.engine.connect() as conn:
        for table, column, col_def in migrations:
            try:
                conn.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                conn.commit()
            except Exception:
                conn.rollback()


app = create_app()

if __name__ == '__main__':
    from scheduler import create_scheduler

    scheduler = create_scheduler()
    scheduler.start()

    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))

    # HTTPS 없이 OAuth 테스트용 (개발 환경)
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
