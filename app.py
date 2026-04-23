import os
import threading
from flask import Flask, jsonify
from config import config
from models import db


def create_app(config_name: str = None) -> Flask:
    app = Flask(__name__)

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'}), 200

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

    # DB 스키마 초기화를 백그라운드에서 실행 — 워커 시작을 블로킹하지 않음
    def _init_db():
        with app.app_context():
            try:
                db.create_all()
                _migrate_schema(db)
                app.logger.info("DB 스키마 초기화 완료")
            except Exception as e:
                app.logger.error("DB 스키마 초기화 실패: %s", e)

    threading.Thread(target=_init_db, daemon=True).start()

    return app


def _migrate_schema(db):
    migrations = [
        ("accounts", "screener_enabled", "BOOLEAN DEFAULT FALSE"),
        ("accounts", "screener_targets", "VARCHAR(128) DEFAULT 'KOSPI,KOSDAQ'"),
        ("accounts", "screener_max_symbols", "INTEGER DEFAULT 5"),
        ("accounts", "screener_per_symbol_limit", "FLOAT DEFAULT 500000.0"),
        ("accounts", "screener_daily_buy_limit", "INTEGER DEFAULT 3"),
        ("accounts", "is_mock", "BOOLEAN DEFAULT FALSE"),
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

    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
