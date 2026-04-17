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

        app.register_blueprint(auth_bp)
        app.register_blueprint(account_bp)
        app.register_blueprint(dashboard_bp)

        db.create_all(checkfirst=True)

    return app


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
