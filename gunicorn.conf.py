"""Gunicorn 설정 — --preload로 앱을 마스터에서 한 번만 로드."""
import logging

workers = 1
bind = "0.0.0.0:5000"
timeout = 300
loglevel = "info"
accesslog = "-"       # 요청 로그를 stdout에 출력해 디버깅 가능
preload_app = True    # 마스터에서 create_app() 1회 실행, 워커는 fork만

_scheduler = None


def post_fork(server, worker):
    log = logging.getLogger(__name__)

    # preload 후 fork 시 마스터의 DB 연결이 워커에 공유되지 않도록 초기화
    try:
        from app import app
        with app.app_context():
            from models import db
            db.engine.dispose()
        log.info("DB engine disposed in worker")
    except Exception as e:
        log.warning("DB engine dispose 실패 (무시): %s", e)

    # 스케줄러는 fork 이후에 시작해야 deadlock 방지
    global _scheduler
    try:
        from scheduler import create_scheduler
        _scheduler = create_scheduler()
        _scheduler.start()
        log.info("APScheduler 시작됨")
    except Exception as e:
        log.error("APScheduler 시작 실패 (워커는 계속 실행): %s", e)


def worker_exit(server, worker):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logging.getLogger(__name__).info("APScheduler 종료됨")
