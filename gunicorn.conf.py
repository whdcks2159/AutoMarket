"""Gunicorn 설정 — --preload로 앱을 마스터에서 한 번만 로드."""
import logging

workers = 1
bind = "0.0.0.0:5000"
timeout = 300
loglevel = "info"
preload_app = True  # 마스터에서 create_app() 1회 실행, 워커는 fork만

_scheduler = None


def post_fork(server, worker):
    # --preload 환경에서 fork 후 SQLAlchemy 연결 풀 초기화 (마스터 연결 오염 방지)
    from app import app
    with app.app_context():
        from models import db
        db.engine.dispose()

    global _scheduler
    from scheduler import create_scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    logging.getLogger(__name__).info("APScheduler 시작됨")


def worker_exit(server, worker):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logging.getLogger(__name__).info("APScheduler 종료됨")
